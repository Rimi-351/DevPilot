"""Common base schemas and pagination structures using Pydantic v2."""

from datetime import datetime
from typing import Generic, Optional, TypeVar

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
    """Query parameters for pagination supporting both page/page_size and skip/limit."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    skip: Optional[int] = Field(default=None, ge=0, description="Offset: number of items to skip")
    limit: Optional[int] = Field(default=None, ge=1, le=100, description="Limit: items per page capped at 100")

    @property
    def offset(self) -> int:
        if self.skip is not None:
            return self.skip
        return (self.page - 1) * self.page_size

    @property
    def effective_limit(self) -> int:
        if self.limit is not None:
            return self.limit
        return self.page_size


class PaginatedResponse(BaseSchema, Generic[T]):
    """Standardized generic paginated response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    skip: Optional[int] = None
    limit: Optional[int] = None
