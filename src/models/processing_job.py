"""ProcessingJob domain model for asynchronous workflows."""

import enum
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.document import Document
    from src.models.project import Project


class JobStatus(str, enum.Enum):
    """Execution status for processing jobs."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ProcessingJob entity tracking asynchronous analysis, indexing, or generation."""

    __tablename__ = "processing_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="processing_jobs")
    document: Mapped[Optional["Document"]] = relationship(
        "Document",
        back_populates="processing_jobs",
    )

    def __repr__(self) -> str:
        return f"<ProcessingJob id={self.id} type='{self.job_type}' status={self.status.value}>"
