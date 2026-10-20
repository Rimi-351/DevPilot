"""DocumentChunk domain model for persistent vector embeddings and text chunks."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.document import Document
    from src.models.project import Project


class DocumentChunk(Base, UUIDPrimaryKeyMixin):
    """DocumentChunk entity representing segmented document content and its embedding."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_project_document", "project_id", "document_id"),
        Index("ix_document_chunks_document_index", "document_id", "chunk_index"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    project: Mapped["Project"] = relationship("Project")

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"
