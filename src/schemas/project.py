"""Pydantic v2 schemas for Project entity."""

from typing import Optional
from uuid import UUID

from pydantic import Field

from src.schemas.common import BaseSchema, TimestampSchema


class ProjectBase(BaseSchema):
    """Shared Project properties."""

    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(default=None, description="Detailed description")


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""

    pass


class ProjectUpdate(BaseSchema):
    """Schema for updating an existing project."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectRead(ProjectBase, TimestampSchema):
    """Schema for reading project data."""

    id: UUID
    tenant_id: Optional[str] = None
