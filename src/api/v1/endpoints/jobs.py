"""ProcessingJob management and status polling REST endpoints."""

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.document import Document
from src.models.processing_job import JobStatus, ProcessingJob
from src.models.project import Project
from src.schemas.common import PaginatedResponse
from src.schemas.processing_job import (
    ProcessingJobCreate,
    ProcessingJobRead,
    ProcessingJobUpdate,
)

router = APIRouter()


@router.post(
    "",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue a new Processing Job",
)
async def create_processing_job(
    job_in: ProcessingJobCreate,
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Register and enqueue a background processing job."""
    # Verify project exists
    project = await db.get(Project, job_in.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{job_in.project_id}' does not exist.",
        )

    # Verify document exists if provided
    if job_in.document_id:
        doc = await db.get(Document, job_in.document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{job_in.document_id}' does not exist.",
            )

    job = ProcessingJob(
        project_id=job_in.project_id,
        document_id=job_in.document_id,
        job_type=job_in.job_type,
        status=JobStatus.PENDING,
        payload=job_in.payload,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


@router.get(
    "",
    response_model=PaginatedResponse[ProcessingJobRead],
    status_code=status.HTTP_200_OK,
    summary="List Processing Jobs with pagination and filters",
)
async def list_processing_jobs(
    project_id: Optional[UUID] = Query(default=None, description="Filter by project ID"),
    job_status: Optional[JobStatus] = Query(default=None, description="Filter by status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve paginated processing jobs ordered by creation date."""
    offset = (page - 1) * page_size

    total_query = select(func.count()).select_from(ProcessingJob)
    data_query = select(ProcessingJob).order_by(ProcessingJob.created_at.desc())

    if project_id:
        total_query = total_query.where(ProcessingJob.project_id == project_id)
        data_query = data_query.where(ProcessingJob.project_id == project_id)
    if job_status:
        total_query = total_query.where(ProcessingJob.status == job_status)
        data_query = data_query.where(ProcessingJob.status == job_status)

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
    "/{job_id}",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_200_OK,
    summary="Get Processing Job status and output",
)
async def get_processing_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Retrieve processing job state by ID."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job with ID '{job_id}' not found.",
        )
    return job


@router.patch(
    "/{job_id}",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_200_OK,
    summary="Update Processing Job state or result",
)
async def update_processing_job(
    job_id: UUID,
    job_in: ProcessingJobUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Update processing status, payload result, or error message."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job with ID '{job_id}' not found.",
        )

    update_data = job_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)

    await db.flush()
    await db.refresh(job)
    return job


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Processing Job",
)
async def delete_processing_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a processing job."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job with ID '{job_id}' not found.",
        )
    await db.delete(job)
