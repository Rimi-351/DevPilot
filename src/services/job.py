"""Job service module providing business logic and object-level authorization for ProcessingJob."""

from __future__ import annotations

import logging
import math
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import verify_project_tenant_access
from src.models.document import Document
from src.models.processing_job import JobStatus, ProcessingJob
from src.models.project import Project
from src.schemas.processing_job import ProcessingJobCreate, ProcessingJobUpdate

logger = logging.getLogger(__name__)


class JobService:
    """Service handling ProcessingJob persistence, lifecycle, and object-level authorization."""

    @staticmethod
    async def verify_job_tenant_access(
        job: ProcessingJob,
        tenant_id: str,
        db: AsyncSession,
    ) -> Project:
        """Verify that the job's parent project belongs to tenant_id.

        Raises:
            HTTPException (404): If the parent project is not found.
            HTTPException (403): If the parent project belongs to another tenant.
        """
        project = await db.get(Project, job.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent project '{job.project_id}' for job '{job.id}' not found.",
            )
        verify_project_tenant_access(project, tenant_id)
        return project

    @staticmethod
    async def create_job(
        job_in: ProcessingJobCreate,
        tenant_id: str,
        db: AsyncSession,
    ) -> ProcessingJob:
        """Create a new processing job verifying parent project ownership."""
        project = await db.get(Project, job_in.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{job_in.project_id}' does not exist.",
            )
        verify_project_tenant_access(project, tenant_id)

        if job_in.document_id:
            doc = await db.get(Document, job_in.document_id)
            if not doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document with ID '{job_in.document_id}' does not exist.",
                )
            if doc.project_id != project.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Document '{job_in.document_id}' does not belong to project '{project.id}'.",
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

    @staticmethod
    async def get_job(
        job_id: UUID,
        tenant_id: str,
        db: AsyncSession,
    ) -> ProcessingJob:
        """Fetch a specific job, enforcing tenant isolation on parent project."""
        job = await db.get(ProcessingJob, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Processing job with ID '{job_id}' not found.",
            )
        await JobService.verify_job_tenant_access(job, tenant_id, db)
        return job

    @staticmethod
    async def list_jobs(
        tenant_id: str,
        db: AsyncSession,
        project_id: Optional[UUID] = None,
        job_status: Optional[JobStatus] = None,
        skip: int = 0,
        limit: int = 20,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> dict[str, Any]:
        """List jobs filtered by tenant ownership with optional project/status filters and deterministic ordering."""
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
            verify_project_tenant_access(project, tenant_id)

            total_query = select(func.count()).select_from(ProcessingJob).where(ProcessingJob.project_id == project_id)
            data_query = select(ProcessingJob).where(ProcessingJob.project_id == project_id)
        else:
            tenant_filter = or_(
                Project.tenant_id == tenant_id,
                Project.owner_api_key == tenant_id,
            )
            total_query = (
                select(func.count())
                .select_from(ProcessingJob)
                .join(Project, ProcessingJob.project_id == Project.id)
                .where(tenant_filter)
            )
            data_query = (
                select(ProcessingJob)
                .join(Project, ProcessingJob.project_id == Project.id)
                .where(tenant_filter)
            )

        if job_status:
            total_query = total_query.where(ProcessingJob.status == job_status)
            data_query = data_query.where(ProcessingJob.status == job_status)

        total_result = await db.execute(total_query)
        total = total_result.scalar_one()

        data_query = (
            data_query.order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.asc())
            .offset(offset)
            .limit(effective_limit)
        )
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

    @staticmethod
    async def update_job(
        job_id: UUID,
        job_in: ProcessingJobUpdate,
        tenant_id: str,
        db: AsyncSession,
    ) -> ProcessingJob:
        """Update job fields with tenant ownership check."""
        job = await db.get(ProcessingJob, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Processing job with ID '{job_id}' not found.",
            )
        await JobService.verify_job_tenant_access(job, tenant_id, db)

        update_data = job_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(job, field, value)

        await db.flush()
        await db.refresh(job)
        return job

    @staticmethod
    async def delete_job(
        job_id: UUID,
        tenant_id: str,
        db: AsyncSession,
    ) -> None:
        """Delete a processing job with tenant check."""
        job = await db.get(ProcessingJob, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Processing job with ID '{job_id}' not found.",
            )
        await JobService.verify_job_tenant_access(job, tenant_id, db)
        await db.delete(job)
