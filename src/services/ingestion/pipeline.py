"""Document ingestion pipeline service for text extraction, chunking, and embedding persistence."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from src.core.config import settings
from src.core.database import async_session_factory
from src.models.document_chunk import DocumentChunk
from src.models.processing_job import JobStatus, ProcessingJob
from src.services.chunker import chunk_text
from src.services.embedding import get_embedding_service
from src.services.extractor import extract_text_from_file

logger = logging.getLogger(__name__)


async def process_document_ingestion(
    job_id: str | UUID,
    document_id: str | UUID,
    project_id: str | UUID,
    file_path: str | Path,
    file_type: str,
    session_factory=None,
) -> ProcessingJob:
    """Execute asynchronous document ingestion lifecycle:
    1. Transition job from PENDING to PROCESSING (recording started_at timestamp).
    2. Extract textual content from file (.pdf, .md, .txt, .py).
    3. Partition text into sliding-window chunks via centralized settings.
    4. Generate vector embeddings for all extracted chunks.
    5. Persist DocumentChunk entities to database.
    6. Transition job to COMPLETED with telemetry payload (recording completed_at).

    Fault Tolerance:
    If any error occurs during reading, parsing, chunking, or embedding,
    the session cleanly rolls back dirty state, transitions job to FAILED,
    records a diagnostic error_message, and sets completed_at.
    """
    factory = session_factory or async_session_factory
    job_uuid = UUID(str(job_id))
    doc_uuid = UUID(str(document_id))
    proj_uuid = UUID(str(project_id))
    file_path_str = str(file_path)

    logger.info("Starting ingestion processing for job %s (doc=%s, proj=%s)", job_id, document_id, project_id)

    # ── 1. Mark PROCESSING and record started_at ─────────────────────────────
    async with factory() as session:
        job = await session.get(ProcessingJob, job_uuid)
        if not job:
            logger.error("ProcessingJob %s not found in database", job_id)
            raise ValueError(f"ProcessingJob {job_id} not found")
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        await session.commit()

    # ── 2. Ingestion Workhorse with Rollback Isolation ───────────────────────
    async with factory() as session:
        job = await session.get(ProcessingJob, job_uuid)
        if not job:
            logger.error("ProcessingJob %s vanished before processing", job_id)
            raise ValueError(f"ProcessingJob {job_id} vanished")

        try:
            # Step A: Text extraction
            text = await extract_text_from_file(file_path_str, file_type=file_type)

            # Step B: Chunking
            chunks = chunk_text(
                text,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )
            chunk_dicts = [c.to_dict() for c in chunks]

            # Step C: Embedding generation
            embedding_service = get_embedding_service()
            chunk_texts = [c.content for c in chunks]
            embeddings = await embedding_service.generate_embeddings(chunk_texts) if chunks else []

            # Step D: Persist document chunks
            if chunks:
                db_chunks = [
                    DocumentChunk(
                        document_id=doc_uuid,
                        project_id=proj_uuid,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        embedding=embeddings[i] if i < len(embeddings) else None,
                    )
                    for i, chunk in enumerate(chunks)
                ]
                session.add_all(db_chunks)

            dimensions = len(embeddings[0]) if embeddings else 0
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = None
            job.result = {
                "chunks_count": len(chunks),
                "chunk_count": len(chunks),   # alias for backward compatibility
                "embedded": True,
                "dimensions": dimensions,
                "total_characters": len(text),
                "chunks_preview": chunk_dicts[:5],
            }
            await session.commit()
            await session.refresh(job)
            logger.info("Job %s COMPLETED successfully with %d chunks", job_id, len(chunks))
            return job

        except Exception as exc:
            logger.exception("Ingestion failed for job %s: %s", job_id, exc)
            await session.rollback()
            try:
                failed_job = await session.get(ProcessingJob, job_uuid)
                if failed_job:
                    failed_job.status = JobStatus.FAILED
                    failed_job.error_message = f"{type(exc).__name__}: {str(exc)[:1000]}"
                    failed_job.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    await session.refresh(failed_job)
                    return failed_job
            except Exception as inner_exc:
                logger.error("Failed to persist failure state for job %s: %s", job_id, inner_exc)
            raise
