"""Document management REST endpoints and multipart upload pipeline."""

import math
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory, get_db
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.processing_job import JobStatus, ProcessingJob
from src.models.project import Project
from src.schemas.common import PaginatedResponse
from src.schemas.document import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    DocumentUploadResponse,
)
from src.services.chunker import chunk_text
from src.services.embedding import get_embedding_service
from src.services.extractor import extract_text_from_file
from src.services.storage import LocalStorageService

router = APIRouter()


async def process_document_background(
    job_id: str,
    document_id: str,
    project_id: str,
    file_path: str,
    file_type: str,
) -> None:
    """Background task: extract text, chunk, embed, and persist DocumentChunk rows.
    Accepts only plain str args (safe for BackgroundTasks serialisation).
    Opens its own DB session — never reuses the closed request session.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(">>> BACKGROUND TASK TRIGGERED FOR JOB: %s", job_id)

    job_uuid = UUID(job_id)

    # ── 1. Mark IN_PROGRESS ──────────────────────────────────────────────────
    async with async_session_factory() as session:
        job = await session.get(ProcessingJob, job_uuid)
        if not job:
            logger.error("ProcessingJob %s not found in DB", job_id)
            return
        job.status = JobStatus.IN_PROGRESS
        await session.commit()

    # ── 2. Process (try/except keeps failures visible) ────────────────────────
    async with async_session_factory() as session:
        job = await session.get(ProcessingJob, job_uuid)
        if not job:
            logger.error("ProcessingJob %s vanished before processing", job_id)
            return
        try:
            # Extract text
            text = await extract_text_from_file(file_path, file_type=file_type)

            # Chunk
            chunks = chunk_text(text)
            chunk_dicts = [c.to_dict() for c in chunks]

            # Embed
            embedding_service = get_embedding_service()
            chunk_texts = [c.content for c in chunks]
            embeddings = await embedding_service.generate_embeddings(chunk_texts)

            # Persist chunks
            if chunks:
                db_chunks = [
                    DocumentChunk(
                        document_id=UUID(document_id),
                        project_id=UUID(project_id),
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
            job.result = {
                "chunks_count": len(chunks),
                "chunk_count": len(chunks),   # alias for backward compatibility
                "embedded": True,
                "dimensions": dimensions,
                "total_characters": len(text),
                "chunks_preview": chunk_dicts[:5],
            }
            await session.commit()
            logger.info("Job %s COMPLETED — %d chunks persisted", job_id, len(chunks))

        except Exception as exc:
            logger.exception("Background processing failed for job %s", job_id)
            job.status = JobStatus.FAILED
            job.error_message = f"{type(exc).__name__}: {exc}"
            await session.commit()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document file",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    project_id: UUID = Form(..., description="Target Project ID"),
    file: UploadFile = File(..., description="File binary (.pdf, .md, .txt, .py)"),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Ingest a multipart file, store binary, create metadata, and queue extraction."""
    # 1. Validate target project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' does not exist.",
        )

    # 2. Read content
    content = await file.read()

    # 3. Persist file via LocalStorageService (validates extension and size)
    storage_service = LocalStorageService()
    saved_path, content_hash, file_size = await storage_service.save_file(
        filename=file.filename or "uploaded_file",
        content=content,
    )

    # 4. Insert Document record
    content_type = file.content_type or "application/octet-stream"
    document = Document(
        project_id=project_id,
        filename=file.filename or "uploaded_file",
        file_path=saved_path,
        file_type=content_type,
        file_size_bytes=file_size,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    # 5. Automatically enqueue ProcessingJob
    job = ProcessingJob(
        project_id=project_id,
        document_id=document.id,
        job_type="document_chunking",
        status=JobStatus.PENDING,
        payload={
            "filename": document.filename,
            "file_path": saved_path,
            "content_hash": content_hash,
        },
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # 6. Commit NOW so the background task's fresh session can see the rows.
    await db.commit()

    # 7. Dispatch background worker – pass plain str values only
    background_tasks.add_task(
        process_document_background,
        job_id=str(job.id),
        document_id=str(document.id),
        project_id=str(project_id),
        file_path=str(saved_path),
        file_type=str(document.file_type),
    )

    return DocumentUploadResponse(
        id=document.id,
        project_id=document.project_id,
        filename=document.filename,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        file_path=document.file_path,
        created_at=document.created_at,
        updated_at=document.updated_at,
        job_id=job.id,
        job_status=job.status.value,
    )


@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Document metadata",
)
async def create_document(
    document_in: DocumentCreate,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Register a new document associated with a project."""
    project = await db.get(Project, document_in.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{document_in.project_id}' does not exist.",
        )

    document = Document(
        project_id=document_in.project_id,
        filename=document_in.filename,
        file_path=document_in.file_path,
        file_type=document_in.file_type,
        file_size_bytes=document_in.file_size_bytes,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    return document


@router.get(
    "",
    response_model=PaginatedResponse[DocumentRead],
    status_code=status.HTTP_200_OK,
    summary="List Documents with pagination and filters",
)
async def list_documents(
    project_id: Optional[UUID] = Query(default=None, description="Filter by project ID"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve paginated list of documents."""
    offset = (page - 1) * page_size

    total_query = select(func.count()).select_from(Document)
    data_query = select(Document).order_by(Document.created_at.desc())

    if project_id:
        total_query = total_query.where(Document.project_id == project_id)
        data_query = data_query.where(Document.project_id == project_id)

    total_result = await db.execute(total_query)
    total = total_result.scalar_one()

    data_query = data_query.offset(offset).limit(page_size)
    result = await db.execute(data_query)
    items = result.scalars().all()

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    status_code=status.HTTP_200_OK,
    summary="Get Document by ID",
)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Retrieve a document by its UUID."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return document


@router.patch(
    "/{document_id}",
    response_model=DocumentRead,
    status_code=status.HTTP_200_OK,
    summary="Update Document metadata",
)
async def update_document(
    document_id: UUID,
    document_in: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Update metadata for an existing document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    update_data = document_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)

    await db.flush()
    await db.refresh(document)
    return document


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document record."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    await db.delete(document)
