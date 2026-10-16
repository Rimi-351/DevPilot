"""Pydantic v2 schemas for Document entity."""

from typing import Optional
from uuid import UUID

from pydantic import Field

from src.schemas.common import BaseSchema, TimestampSchema


class DocumentBase(BaseSchema):
    """Shared Document properties."""

    filename: str = Field(..., min_length=1, max_length=255, description="Document filename")
    file_type: str = Field(..., min_length=1, max_length=64, description="MIME type or extension")
    file_path: Optional[str] = Field(default=None, max_length=1024, description="Storage location/URI")
    file_size_bytes: Optional[int] = Field(default=None, ge=0, description="Size in bytes")


class DocumentCreate(DocumentBase):
    """Schema for registering a new document."""

    project_id: UUID = Field(..., description="Associated project ID")


class DocumentUpdate(BaseSchema):
    """Schema for updating document metadata."""

    filename: Optional[str] = Field(default=None, min_length=1, max_length=255)
    file_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    file_path: Optional[str] = Field(default=None, max_length=1024)
    file_size_bytes: Optional[int] = Field(default=None, ge=0)


class DocumentRead(DocumentBase, TimestampSchema):
    """Schema for reading document data."""

    id: UUID
    project_id: UUID
