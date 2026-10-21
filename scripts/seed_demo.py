"""Seed automated sample documents into a demo evaluation workspace for DevPilot."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import uuid4

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory, engine
from src.models.base import Base
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.processing_job import JobStatus, ProcessingJob
from src.models.project import Project
from src.services.ingestion.pipeline import process_document_ingestion
from src.services.storage import LocalStorageService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_demo")

DEFAULT_PROJECT_NAME = "DevPilot Evaluation Workspace"
DEFAULT_DEMO_KEY = "devpilot-demo-key"

SAMPLE_DOCUMENTS = [
    {
        "filename": "architecture_overview.md",
        "title": "DevPilot Architecture & Core Technical Components",
        "content": """# DevPilot Architecture Overview

DevPilot is an enterprise-grade AI document intelligence platform built with asynchronous Python, FastAPI, and SQLAlchemy 2.0.

## 1. System Architecture
- **API & Routing Layer:** FastAPI ASGI framework offering non-blocking request concurrency and declarative Pydantic schemas.
- **Storage & Ingestion:** LocalStorageService calculates SHA-256 digests and validates upload quotas (10MB limit). A sliding-window chunker (512 characters, 64-character overlap) partitions documents without boundary truncation.
- **Data Persistence:** Asynchronous connection pooling via asyncpg (PostgreSQL 16) with seamless SQLite fallback for zero-dependency local evaluations.
- **Multi-Tenant Security:** Strict object-level authorization enforcing HTTP 401 on unauthenticated ingress and HTTP 403 on cross-tenant access.

## 2. Hybrid Retrieval Pipeline
DevPilot employs a state-of-the-art hybrid consensus search strategy:
1. **Dense Vector Search:** FastEmbed generating 384-dimensional multilingual embeddings (`paraphrase-multilingual-MiniLM-L12-v2`).
2. **Sparse Lexical Search:** In-memory cached BM25Okapi using multilingual Unicode regex tokenization supporting Bengali and Latin scripts.
3. **Reciprocal Rank Fusion (RRF):** Merges candidate lists using constant k=60.
4. **Cross-Encoder Reranker:** Neural reranker (`mmarco-mMiniLMv2-L12-H384-v1`) blended with 20% RRF consensus achieving superior 0.8748 Global MRR.
""",
    },
    {
        "filename": "api_reference.md",
        "title": "DevPilot REST API Reference & Security Model",
        "content": """# DevPilot REST API Reference

All protected endpoints in DevPilot require an `X-API-Key` header representing the caller tenant.

## Key Endpoints
- `GET /api/v1/health`: Public service health and database ping.
- `POST /api/v1/projects`: Creates an isolated workspace mapped to the authenticated tenant.
- `GET /api/v1/projects`: Lists tenant projects with bounded pagination (`skip >= 0`, `1 <= limit <= 100`).
- `POST /api/v1/documents/upload`: Multipart document upload returning an async processing job ID.
- `GET /api/v1/jobs/{id}`: Polls processing job lifecycle status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).
- `POST /api/v1/projects/{id}/search`: Executes multi-mode semantic search (`vector_only`, `hybrid`, `hybrid_rerank`).
- `POST /api/v1/projects/{id}/rag`: Grounded answer synthesis with inline citations and anti-hallucination guardrails.
- `POST /api/v1/projects/{id}/agent/workflow`: Runs bounded 4-phase research agent (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`).

## Guardrails & Citation Verification
The CitationVerificationService automatically inspects generated answers, strips hallucinated citation tags, computes the unsupported claims rate, and guarantees polite negative refusals when documents lack sufficient context.
""",
    },
    {
        "filename": "multilingual_capabilities.md",
        "title": "Multilingual Retrieval & Bengali Script Optimization",
        "content": """# Multilingual Retrieval & Bengali Script Optimization

DevPilot natively supports cross-lingual document intelligence across English, native Bengali script, and Romanized Banglish.

## Script-Aware Routing
- Native Bengali text matching `[\\u0980-\\u09ff]` is routed dynamically to optimize latency and memory footprint.
- BM25 tokenizer employs a custom Unicode pattern: `[\\w\\u0980-\\u09ff\\u200c\\u200d]+` preserving conjunct characters and zero-width joiners.

## Evaluation Benchmark Performance
Across our 100-query multilingual gold standard benchmark (`benchmarks/multilingual_gold_100.jsonl`):
- **English Slice (34 queries):** 1.00 Recall@5, 0.8284 MRR
- **Bengali Script Slice (33 queries):** 0.98 Recall@5, 0.8581 MRR
- **Banglish Slice (33 queries):** 1.00 Recall@5, 0.9394 MRR
- **Production Champion:** Approach A+B Hybrid consensus achieves 80.0% Rank #1 precision with sub-second P95 latencies.
""",
    },
]


async def seed_demo_workspace(
    project_name: str = DEFAULT_PROJECT_NAME,
    api_key: str = DEFAULT_DEMO_KEY,
    force_reseed: bool = False,
) -> dict:
    """Provisions a demo project, uploads sample documents, and runs ingestion."""
    # 1. Ensure database tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    storage_service = LocalStorageService()

    async with async_session_factory() as session:
        # 2. Check for existing demo project
        stmt = select(Project).where(
            Project.name == project_name,
            Project.tenant_id == api_key,
        )
        result = await session.execute(stmt)
        project = result.scalars().first()

        if project and not force_reseed:
            logger.info("Found existing demo project '%s' (ID: %s)", project.name, project.id)
        else:
            if not project:
                project = Project(
                    id=uuid4(),
                    name=project_name,
                    description="Automated demo evaluation workspace provisioned with technical architecture and benchmark notes.",
                    tenant_id=api_key,
                    owner_api_key=api_key,
                )
                session.add(project)
                await session.commit()
                await session.refresh(project)
                logger.info("Created new demo project '%s' (ID: %s)", project.name, project.id)

        project_id = project.id

        # 3. Seed sample documents and execute ingestion pipeline
        seeded_docs_summary = []

        for sample in SAMPLE_DOCUMENTS:
            filename = sample["filename"]
            content_bytes = sample["content"].strip().encode("utf-8")

            # Check if document already exists in this project
            doc_stmt = select(Document).where(
                Document.project_id == project_id,
                Document.filename == filename,
            )
            doc_res = await session.execute(doc_stmt)
            existing_doc = doc_res.scalars().first()

            if existing_doc and not force_reseed:
                logger.info("Document '%s' already exists for project. Verifying chunks...", filename)
                doc = existing_doc
            else:
                # Save file via LocalStorageService
                saved_path, _, file_size = await storage_service.save_file(
                    filename=filename,
                    content=content_bytes,
                )

                doc = Document(
                    id=uuid4(),
                    project_id=project_id,
                    filename=filename,
                    file_path=saved_path,
                    file_type=".md",
                    file_size_bytes=file_size,
                )
                session.add(doc)

                job = ProcessingJob(
                    id=uuid4(),
                    project_id=project_id,
                    document_id=doc.id,
                    job_type="document_ingestion",
                    status=JobStatus.PENDING,
                    payload={"filename": filename, "source": "seed_demo"},
                )
                session.add(job)
                await session.commit()
                await session.refresh(doc)
                await session.refresh(job)

                logger.info("Triggering ingestion pipeline for '%s' (Job: %s)...", filename, job.id)
                await process_document_ingestion(
                    job_id=job.id,
                    document_id=doc.id,
                    project_id=project_id,
                    file_path=saved_path,
                    file_type=".md",
                    session_factory=async_session_factory,
                )

            # 4. Verify chunking and embedding persistence
            chunks_stmt = select(DocumentChunk).where(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.project_id == project_id,
            )
            chunks_res = await session.execute(chunks_stmt)
            chunks = chunks_res.scalars().all()

            assert len(chunks) > 0, f"No chunks were generated for {filename}!"
            for c in chunks:
                assert c.embedding is not None and len(c.embedding) > 0, (
                    f"Chunk {c.chunk_index} of {filename} is missing vector embeddings!"
                )

            seeded_docs_summary.append(
                {
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "chunks_count": len(chunks),
                    "embedding_dim": len(chunks[0].embedding),
                }
            )
            logger.info("Verified '%s': %d chunks indexed with valid embeddings.", filename, len(chunks))

        summary = {
            "status": "SUCCESS",
            "project_id": str(project_id),
            "project_name": project.name,
            "tenant_id": api_key,
            "documents_seeded": len(seeded_docs_summary),
            "documents": seeded_docs_summary,
        }
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo workspace and sample documents for DevPilot.")
    parser.add_argument(
        "--project-name",
        type=str,
        default=DEFAULT_PROJECT_NAME,
        help=f"Name of the demo project (default: '{DEFAULT_PROJECT_NAME}')",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=DEFAULT_DEMO_KEY,
        help=f"Tenant API key for demo access (default: '{DEFAULT_DEMO_KEY}')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-seeding even if project already exists",
    )
    args = parser.parse_args()

    summary = asyncio.run(
        seed_demo_workspace(
            project_name=args.project_name,
            api_key=args.api_key,
            force_reseed=args.force,
        )
    )

    print("\n" + "=" * 80)
    print("DevPilot Demo Workspace Seeding Complete")
    print("=" * 80)
    print(f"Project Name : {summary['project_name']}")
    print(f"Project ID   : {summary['project_id']}")
    print(f"Tenant Key   : {summary['tenant_id']} (use header 'X-API-Key: {summary['tenant_id']}')")
    print("-" * 80)
    print("Seeded Documents & Verified Chunks:")
    for doc in summary["documents"]:
        print(f"  • {doc['filename']} (ID: {doc['document_id']}) -> {doc['chunks_count']} chunks, dim={doc['embedding_dim']}")
    print("=" * 80)
    print(f"\nQuick Test Query via cURL:")
    print(f"curl -X POST http://localhost:8000/api/v1/projects/{summary['project_id']}/rag \\")
    print(f"  -H 'X-API-Key: {summary['tenant_id']}' \\")
    print(f"  -H 'Content-Type: application/json' \\")
    print(f"  -d '{{\"query\": \"What is the architecture of DevPilot?\"}}'")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
