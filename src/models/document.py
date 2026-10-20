"""Document domain model."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.document_chunk import DocumentChunk
    from src.models.processing_job import ProcessingJob
    from src.models.project import Project


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Document entity representing an uploaded or tracked file within a project."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_project_created", "project_id", "created_at"),
        Index("ix_documents_project_filename", "project_id", "filename"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="documents")
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob",
        back_populates="document",
        lazy="selectin",
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename='{self.filename}' project_id={self.project_id}>"
