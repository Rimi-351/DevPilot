"""ProcessingJob management and status polling REST endpoints with multi-tenant isolation."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_tenant
from src.models.processing_job import JobStatus, ProcessingJob
from src.schemas.common import PaginatedResponse
from src.schemas.processing_job import (
    ProcessingJobCreate,
    ProcessingJobRead,
    ProcessingJobUpdate,
)
from src.services.job import JobService

router = APIRouter()


@router.post(
    "",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue a new Processing Job",
)
async def create_processing_job(
    job_in: ProcessingJobCreate,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Register and enqueue a background processing job with tenant isolation."""
    return await JobService.create_job(job_in=job_in, tenant_id=tenant_id, db=db)


@router.get(
    "",
    response_model=PaginatedResponse[ProcessingJobRead],
    status_code=status.HTTP_200_OK,
    summary="List Processing Jobs with bounded deterministic pagination",
)
async def list_processing_jobs(
    project_id: Optional[UUID] = Query(default=None, description="Filter by project ID"),
    job_status: Optional[JobStatus] = Query(default=None, description="Filter by status"),
    skip: int = Query(default=0, ge=0, description="Offset: number of items to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Limit: items per page capped at 100"),
    page: Optional[int] = Query(default=None, ge=1, description="Page number (1-indexed)"),
    page_size: Optional[int] = Query(default=None, ge=1, le=100, description="Items per page"),
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve paginated processing jobs scoped strictly to the authenticated tenant."""
    return await JobService.list_jobs(
        tenant_id=tenant_id,
        db=db,
        project_id=project_id,
        job_status=job_status,
        skip=skip,
        limit=limit,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{job_id}",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_200_OK,
    summary="Get Processing Job status and output",
)
async def get_processing_job(
    job_id: UUID,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Retrieve processing job state by ID with parent project tenant verification."""
    return await JobService.get_job(job_id=job_id, tenant_id=tenant_id, db=db)


@router.patch(
    "/{job_id}",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_200_OK,
    summary="Update Processing Job state or result",
)
async def update_processing_job(
    job_id: UUID,
    job_in: ProcessingJobUpdate,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Update processing status, payload result, or error message with tenant check."""
    return await JobService.update_job(job_id=job_id, job_in=job_in, tenant_id=tenant_id, db=db)


@router.patch(
    "/{job_id}/status",
    response_model=ProcessingJobRead,
    status_code=status.HTTP_200_OK,
    summary="Update Processing Job status with tenant ownership check",
)
async def update_processing_job_status(
    job_id: UUID,
    job_in: ProcessingJobUpdate,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    """Dedicated endpoint to update job status and payload with strict tenant authorization."""
    return await JobService.update_job(job_id=job_id, job_in=job_in, tenant_id=tenant_id, db=db)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Processing Job",
)
async def delete_processing_job(
    job_id: UUID,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a processing job with parent project tenant ownership check."""
    await JobService.delete_job(job_id=job_id, tenant_id=tenant_id, db=db)
