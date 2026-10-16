"""Document management REST endpoints."""

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.document import Document
from src.models.project import Project
from src.schemas.common import PaginatedResponse
from src.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate

router = APIRouter()


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
    # Validate target project exists
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
