"""Search Pydantic v2 schemas for semantic retrieval and provenance."""

from uuid import UUID

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SearchQueryRequest(BaseModel):
    """Search query request payload."""

    query: str = Field(..., min_length=1, description="Semantic search query text")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of relevant chunks to return",
    )
    mode: Literal["keyword", "vector", "hybrid", "hybrid_rerank"] = Field(
        default="vector",
        description="Retrieval mode: keyword, vector, hybrid, or hybrid_rerank",
    )


class SearchChunkResult(BaseModel):
    """Individual chunk search result with full provenance."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID = Field(..., description="Unique chunk identifier")
    document_id: UUID = Field(..., description="Parent document identifier")
    filename: str = Field(..., description="Original filename of the document")
    content: str = Field(..., description="Text segment content")
    score: float = Field(..., description="Cosine similarity score")
    start_offset: int = Field(
        ...,
        description="Starting character offset in source document",
    )
    end_offset: int = Field(
        ...,
        description="Ending character offset in source document",
    )
    chunk_index: int = Field(..., description="Sequential chunk index")


class SearchResponse(BaseModel):
    """Semantic search response payload."""

    query: str = Field(..., description="Search query executed")
    total_results: int = Field(..., description="Number of results returned")
    results: list[SearchChunkResult] = Field(
        default_factory=list,
        description="Ranked list of chunk matches",
    )
