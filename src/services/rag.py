"""Grounded RAG synthesis service with citation verification and anti-hallucination guardrails."""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.guardrails import CitationVerificationService, get_citation_verification_service
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.schemas.rag import Citation, RagResponse
from src.services.llm import LLMService, NEGATIVE_RESPONSE, get_llm_service
from src.services.retrieval import retrieve_chunks

logger = logging.getLogger(__name__)


class RagService:
    """Service orchestrating semantic retrieval, LLM synthesis, citation verification,

    and anti-hallucination guardrails for multi-tenant projects.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        guardrail_service: Optional[CitationVerificationService] = None,
    ) -> None:
        self.llm_service = llm_service or get_llm_service()
        self.guardrail_service = guardrail_service or get_citation_verification_service()

    async def generate_grounded_answer(
        self,
        query: str,
        project_id: UUID,
        session: AsyncSession,
        search_mode: str = "vector_only",
        top_k: int = 3,
        temperature: float = 0.0,
        chunk_limit: int = 10,
        strip_invalid_citations: bool = True,
    ) -> RagResponse:
        """Perform semantic retrieval, synthesize an answer with citations, and apply

        anti-hallucination guardrails to verify source provenance.

        Args:
            query: Question submitted by user.
            project_id: Unique project identifier.
            session: Injected database session.
            search_mode: Retrieval search mode ('vector_only', 'hybrid', 'hybrid_rerank').
            top_k: Number of top relevant chunks to retain for context.
            temperature: LLM generation temperature.
            chunk_limit: Candidate pool size before reranking/RRF.
            strip_invalid_citations: Whether to strip invalid citations automatically.

        Returns:
            RagResponse containing answer, citations, chunks evaluated, and grounding metrics.
        """
        # Early guard: empty or whitespace-only query or non-positive top_k
        if not query or not query.strip() or top_k <= 0:
            return RagResponse(
                query=query,
                answer=NEGATIVE_RESPONSE,
                citations=[],
                chunks_evaluated=0,
                search_mode=search_mode,
                is_grounded=True,
                unsupported_claims_rate=0.0,
                citation_correctness=1.0,
                invalid_citations_stripped=[],
            )

        # 1. Fetch chunks belonging to project joined with Document for original filename
        stmt = (
            select(DocumentChunk, Document.filename)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.project_id == project_id)
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            return RagResponse(
                query=query,
                answer=NEGATIVE_RESPONSE,
                citations=[],
                chunks_evaluated=0,
                search_mode=search_mode,
                is_grounded=True,
                unsupported_claims_rate=0.0,
                citation_correctness=1.0,
                invalid_citations_stripped=[],
            )

        # 2. Format candidate chunk dictionaries with safe defaults
        candidate_chunks: list[dict[str, Any]] = []
        for chunk, filename in rows:
            candidate_chunks.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "filename": filename or "unknown",
                "content": chunk.content or "",
                "start_offset": chunk.start_offset if chunk.start_offset is not None else 0,
                "end_offset": chunk.end_offset if chunk.end_offset is not None else 0,
                "chunk_index": chunk.chunk_index if chunk.chunk_index is not None else 0,
                "embedding": chunk.embedding or [],
            })

        # 3. Multi-mode retrieval
        ranked_chunks = await retrieve_chunks(
            query=query,
            chunks=candidate_chunks,
            search_mode=search_mode,
            top_k=top_k,
            chunk_limit=max(1, chunk_limit),
        )

        if not ranked_chunks:
            return RagResponse(
                query=query,
                answer=NEGATIVE_RESPONSE,
                citations=[],
                chunks_evaluated=0,
                search_mode=search_mode,
                is_grounded=True,
                unsupported_claims_rate=0.0,
                citation_correctness=1.0,
                invalid_citations_stripped=[],
            )

        # 4. Format context excerpts with 1-based citation indices [1], [2], ...
        context_chunks: list[dict[str, Any]] = []
        for idx, c in enumerate(ranked_chunks, start=1):
            item = dict(c)
            item["index"] = idx
            context_chunks.append(item)

        # 5. Call LLM service to synthesize answer
        raw_answer, _ = await self.llm_service.generate_grounded_answer(
            query=query,
            context_chunks=context_chunks,
            temperature=temperature,
        )

        # 6. Apply post-processing citation verification and anti-hallucination guardrails
        guardrail_result = self.guardrail_service.verify_and_filter_citations(
            raw_answer=raw_answer,
            context_chunks=context_chunks,
            strip_invalid=strip_invalid_citations,
        )

        # 7. Map verified citations to Citation models with safe offsets
        citations: list[Citation] = []
        for idx, c in enumerate(guardrail_result.valid_citations, start=1):
            start_off = c.get("start_offset")
            end_off = c.get("end_offset")
            citations.append(
                Citation(
                    citation_id=int(c.get("index") or idx),
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    filename=c.get("filename") or "unknown",
                    start_offset=start_off if start_off is not None else 0,
                    end_offset=end_off if end_off is not None else 0,
                    content=c.get("content"),
                    score=float(c.get("score")) if c.get("score") is not None else None,
                )
            )

        return RagResponse(
            query=query,
            answer=guardrail_result.cleaned_answer,
            citations=citations,
            chunks_evaluated=len(context_chunks),
            search_mode=search_mode,
            is_grounded=guardrail_result.is_grounded,
            unsupported_claims_rate=guardrail_result.unsupported_claims_rate,
            citation_correctness=guardrail_result.citation_correctness,
            invalid_citations_stripped=guardrail_result.invalid_citations,
        )


_default_rag_service: Optional[RagService] = None


def get_rag_service() -> RagService:
    """Return singleton instance of RagService."""
    global _default_rag_service
    if _default_rag_service is None:
        _default_rag_service = RagService()
    return _default_rag_service


__all__ = [
    "RagService",
    "get_rag_service",
]
