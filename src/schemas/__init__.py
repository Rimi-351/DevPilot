"""Pydantic v2 schemas registry."""

from src.schemas.common import (
    BaseSchema,
    PaginatedResponse,
    PaginationParams,
    TimestampSchema,
)
from src.schemas.document import (
    DocumentBase,
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    DocumentUploadResponse,
)
from src.schemas.processing_job import (
    JobStatus,
    ProcessingJobBase,
    ProcessingJobCreate,
    ProcessingJobRead,
    ProcessingJobUpdate,
)
from src.schemas.project import (
    ProjectBase,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)

__all__ = [
    "BaseSchema",
    "TimestampSchema",
    "PaginationParams",
    "PaginatedResponse",
    "ProjectBase",
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectRead",
    "DocumentBase",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentRead",
    "DocumentUploadResponse",
    "JobStatus",
    "ProcessingJobBase",
    "ProcessingJobCreate",
    "ProcessingJobUpdate",
    "ProcessingJobRead",
]
