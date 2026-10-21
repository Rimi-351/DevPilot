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

from src.core.config import settings
from src.core.database import async_session_factory, get_db
from src.core.security import get_current_api_key, is_demo_api_key, verify_project_tenant_access
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

from src.services.ingestion.pipeline import process_document_ingestion

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
    Delegates to resilient process_document_ingestion pipeline with transactional isolation.
    """
    try:
        await process_document_ingestion(
            job_id=job_id,
            document_id=document_id,
            project_id=project_id,
            file_path=file_path,
            file_type=file_type,
            session_factory=async_session_factory,
        )
    except Exception:
        # State machine transition to FAILED and session rollback handled inside pipeline
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
    api_key: str = Depends(get_current_api_key),
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
    verify_project_tenant_access(project, api_key)

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
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Register a new document associated with a project."""
    project = await db.get(Project, document_in.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{document_in.project_id}' does not exist.",
        )
    verify_project_tenant_access(project, api_key)

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
    summary="List Documents with bounded deterministic pagination",
)
async def list_documents(
    project_id: Optional[UUID] = Query(default=None, description="Filter by project ID"),
    skip: int = Query(default=0, ge=0, description="Offset: number of items to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Limit: items per page capped at 100"),
    page: Optional[int] = Query(default=None, ge=1, description="Page number (1-indexed)"),
    page_size: Optional[int] = Query(default=None, ge=1, le=100, description="Items per page"),
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve paginated list of documents with tenant isolation and deterministic ordering."""
    if page is not None and (skip == 0 or skip is None):
        effective_page_size = page_size if page_size is not None else limit
        offset = (page - 1) * effective_page_size
        effective_limit = effective_page_size
    elif page_size is not None and limit == 20:
        offset = skip
        effective_limit = page_size
    else:
        offset = skip
        effective_limit = limit

    if project_id:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' does not exist.",
            )
        verify_project_tenant_access(project, api_key)

        total_query = select(func.count()).select_from(Document).where(Document.project_id == project_id)
        data_query = (
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc(), Document.id.asc())
        )
    else:
        if is_demo_api_key(api_key):
            tenant_filter = (
                (Project.tenant_id == api_key)
                | (Project.owner_api_key == api_key)
                | (Project.name == "DevPilot Evaluation Workspace")
                | (Project.tenant_id == "devpilot-demo-key")
                | (Project.tenant_id.is_(None))
            )
        else:
            tenant_filter = (
                (Project.tenant_id == api_key)
                | (Project.owner_api_key == api_key)
                | (Project.tenant_id.is_(None))
            )
        total_query = (
            select(func.count())
            .select_from(Document)
            .join(Project, Document.project_id == Project.id)
            .where(tenant_filter)
        )
        data_query = (
            select(Document)
            .join(Project, Document.project_id == Project.id)
            .where(tenant_filter)
            .order_by(Document.created_at.desc(), Document.id.asc())
        )

    total_result = await db.execute(total_query)
    total = total_result.scalar_one()

    data_query = data_query.offset(offset).limit(effective_limit)
    result = await db.execute(data_query)
    items = result.scalars().all()

    total_pages = math.ceil(total / effective_limit) if total > 0 else 0
    page_computed = (offset // effective_limit) + 1 if effective_limit > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page_computed,
        "page_size": effective_limit,
        "total_pages": total_pages,
        "skip": offset,
        "limit": effective_limit,
    }


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    status_code=status.HTTP_200_OK,
    summary="Get Document by ID",
)
async def get_document(
    document_id: UUID,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Retrieve a document by its UUID."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    project = await db.get(Project, document.project_id)
    if project:
        verify_project_tenant_access(project, api_key)
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
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Update metadata for an existing document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    project = await db.get(Project, document.project_id)
    if project:
        verify_project_tenant_access(project, api_key)

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
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document record."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    project = await db.get(Project, document.project_id)
    if project:
        verify_project_tenant_access(project, api_key)
    await db.delete(document)
