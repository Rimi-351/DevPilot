"""Project domain model."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.document import Document
    from src.models.processing_job import ProcessingJob


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Project entity representing a top-level workspace or repository."""

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_tenant_created", "tenant_id", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    owner_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name='{self.name}'>"
