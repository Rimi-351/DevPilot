"""Common base schemas and pagination structures using Pydantic v2."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema enforcing Pydantic v2 attributes configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class TimestampSchema(BaseSchema):
    """Schema containing timestamp metadata."""

    created_at: datetime
    updated_at: datetime


class PaginationParams(BaseSchema):
    """Query parameters for pagination."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseSchema, Generic[T]):
    """Standardized generic paginated response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
