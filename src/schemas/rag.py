"""RAG Pydantic v2 schemas for grounded queries, citations, and responses."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RagQueryRequest(BaseModel):
    """RAG query request payload."""

    query: str = Field(..., min_length=1, description="Question or query string")
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top relevant chunks to retrieve for context",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM generation temperature (0.0 for deterministic grounding)",
    )
    search_mode: str = Field(
        default="vector_only",
        description="Retrieval search mode: 'vector_only', 'hybrid', or 'hybrid_rerank'",
    )
    chunk_limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Candidate pool size for initial retrieval before RRF or reranking",
    )


class Citation(BaseModel):
    """Citation provenance linking a factual claim to its source document chunk."""

    model_config = ConfigDict(from_attributes=True)

    citation_id: int = Field(..., description="Sequential citation identifier matching [X] in answer")
    chunk_id: UUID = Field(..., description="Unique document chunk identifier")
    document_id: UUID = Field(..., description="Parent document identifier")
    filename: str = Field(..., description="Original filename of the source document")
    start_offset: int = Field(..., description="Starting character offset in source document")
    end_offset: int = Field(..., description="Ending character offset in source document")


class RagResponse(BaseModel):
    """Grounded RAG synthesis response payload with citation provenance."""

    query: str = Field(..., description="User query submitted")
    answer: str = Field(..., description="Grounded answer containing citation markers or negative rejection")
    citations: list[Citation] = Field(
        default_factory=list,
        description="List of document chunk citations supporting the generated claims",
    )
    chunks_evaluated: int = Field(
        ...,
        description="Total number of retrieved context chunks evaluated",
    )
    search_mode: str = Field(
        default="vector_only",
        description="Search mode executed for retrieval",
    )
