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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import get_db, get_session_factory
from src.models.document import Document
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
from src.services.extractor import extract_text_from_file
from src.services.storage import LocalStorageService

router = APIRouter()


async def process_document_background(
    job_id: UUID,
    file_path: str,
    file_type: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Background task to extract text, calculate chunks, and update job status."""
    async with session_factory() as session:
        try:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                return

            job.status = JobStatus.IN_PROGRESS
            await session.commit()

            # Extract content from persisted file
            text = await extract_text_from_file(file_path, file_type=file_type)

            # Generate chunks with offsets
            chunks = chunk_text(text)
            chunk_dicts = [c.to_dict() for c in chunks]

            job.status = JobStatus.COMPLETED
            job.result = {
                "chunk_count": len(chunks),
                "total_characters": len(text),
                "chunks_preview": chunk_dicts[:5],
            }
            await session.commit()
        except Exception as exc:
            await session.rollback()
            try:
                job = await session.get(ProcessingJob, job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(exc)
                    await session.commit()
            except Exception:
                pass


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
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
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

    # 6. Dispatch background worker
    background_tasks.add_task(
        process_document_background,
        job_id=job.id,
        file_path=saved_path,
        file_type=document.file_type,
        session_factory=session_factory,
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
