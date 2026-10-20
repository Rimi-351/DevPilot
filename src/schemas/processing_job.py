"""Pydantic v2 schemas for ProcessingJob entity."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from src.models.processing_job import JobStatus
from src.schemas.common import BaseSchema, TimestampSchema


class ProcessingJobBase(BaseSchema):
    """Shared ProcessingJob properties."""

    project_id: UUID = Field(..., description="Target project ID")
    document_id: Optional[UUID] = Field(default=None, description="Optional target document ID")
    job_type: str = Field(..., min_length=1, max_length=64, description="Type of background job")
    payload: Optional[dict[str, Any]] = Field(default=None, description="Input parameters/payload")


class ProcessingJobCreate(ProcessingJobBase):
    """Schema for triggering or registering a processing job."""

    pass


class ProcessingJobUpdate(BaseSchema):
    """Schema for updating processing job state or output."""

    status: Optional[JobStatus] = None
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProcessingJobRead(ProcessingJobBase, TimestampSchema):
    """Schema for reading processing job status and results."""

    id: UUID
    status: JobStatus
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
