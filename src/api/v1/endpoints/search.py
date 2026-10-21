"""Search API endpoints for semantic similarity retrieval and document provenance."""

import math
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_api_key, verify_project_tenant_access
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.project import Project
from src.schemas.search import SearchChunkResult, SearchQueryRequest, SearchResponse
from src.services.embedding import get_embedding_service

router = APIRouter()


def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    if not vec1 or not vec2:
        return 0.0

    length = min(len(vec1), len(vec2))
    dot_product = sum(vec1[i] * vec2[i] for i in range(length))
    norm1 = math.sqrt(sum(x * x for x in vec1[:length]))
    norm2 = math.sqrt(sum(y * y for y in vec2[:length]))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    similarity = dot_product / (norm1 * norm2)
    return float(max(-1.0, min(1.0, similarity)))


@router.post(
    "/{project_id}/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic search within project documents",
)
async def search_project_documents(
    project_id: UUID,
    request: SearchQueryRequest,
    api_key: str = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Execute vector cosine-similarity search over document chunks in a project with tenant isolation."""
    # 1. Verify project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' does not exist.",
        )
    verify_project_tenant_access(project, api_key)

    # Fast path: Empty or whitespace-only search query returns 0 results
    if not request.query or not request.query.strip():
        return SearchResponse(
            query=request.query,
            total_results=0,
            results=[],
        )

    # 2. Retrieve or compute query representation based on mode
    if request.mode == "vector":
        # Vector mode: generate embedding
        embedding_service = get_embedding_service()
        query_vector = await embedding_service.generate_query_embedding(request.query)
    else:
        # Keyword mode: no embedding needed
        query_vector = []

    # 3. Fetch all DocumentChunk records belonging to project joined with Document for filename
    stmt = (
        select(DocumentChunk, Document.filename)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.project_id == project_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 4. Rank chunks based on selected retrieval mode
    scored_results: list[SearchChunkResult] = []
    if request.mode in ("hybrid", "hybrid_rerank"):
        from src.services.retrieval import retrieve_chunks

        candidate_chunks = [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "filename": filename or "unknown",
                "content": chunk.content or "",
                "start_offset": chunk.start_offset if chunk.start_offset is not None else 0,
                "end_offset": chunk.end_offset if chunk.end_offset is not None else 0,
                "chunk_index": chunk.chunk_index if chunk.chunk_index is not None else 0,
                "embedding": chunk.embedding or [],
            }
            for chunk, filename in rows
        ]
        retrieved = await retrieve_chunks(
            query=request.query,
            chunks=candidate_chunks,
            search_mode=request.mode,
            top_k=request.top_k,
        )
        for c in retrieved:
            final_score = float(c.get("rerank_score", c.get("rrf_score", c.get("score", 0.0))))
            scored_results.append(
                SearchChunkResult(
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    filename=c.get("filename") or "unknown",
                    content=c.get("content") or "",
                    score=round(final_score, 6),
                    start_offset=c.get("start_offset") if c.get("start_offset") is not None else 0,
                    end_offset=c.get("end_offset") if c.get("end_offset") is not None else 0,
                    chunk_index=c.get("chunk_index") if c.get("chunk_index") is not None else 0,
                )
            )
        return SearchResponse(
            query=request.query,
            total_results=len(scored_results),
            results=scored_results,
        )
    elif request.mode == "keyword":
        # Keyword baseline: compute lexical overlap scores
        from src.services.search import lexical_keyword_search
        # Extract pure DocumentChunk objects
        chunks = [chunk for chunk, _ in rows]
        ranked_chunks = lexical_keyword_search(request.query, chunks)
        # Map chunk IDs to filenames for provenance
        chunk_id_to_filename = {chunk.id: (filename or "unknown") for chunk, filename in rows}
        query_tokens = set(re.findall(r"\w+", request.query.lower()))
        for chunk in ranked_chunks:
            filename = chunk_id_to_filename.get(chunk.id, "unknown")
            chunk_tokens = set(re.findall(r"\w+", chunk.content.lower()))
            overlap = len(query_tokens & chunk_tokens)
            score = overlap / max(len(query_tokens), 1)
            scored_results.append(
                SearchChunkResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=filename,
                    content=chunk.content or "",
                    score=round(score, 6),
                    start_offset=chunk.start_offset if chunk.start_offset is not None else 0,
                    end_offset=chunk.end_offset if chunk.end_offset is not None else 0,
                    chunk_index=chunk.chunk_index if chunk.chunk_index is not None else 0,
                )
            )
    else:
        # Vector mode: original cosine similarity scoring
        for chunk, filename in rows:
            chunk_embedding = chunk.embedding or []
            score = compute_cosine_similarity(query_vector, chunk_embedding)
            scored_results.append(
                SearchChunkResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=filename or "unknown",
                    content=chunk.content or "",
                    score=round(score, 6),
                    start_offset=chunk.start_offset if chunk.start_offset is not None else 0,
                    end_offset=chunk.end_offset if chunk.end_offset is not None else 0,
                    chunk_index=chunk.chunk_index if chunk.chunk_index is not None else 0,
                )
            )

    # 5. Sort descending and pick top_k safely
    scored_results.sort(key=lambda item: item.score, reverse=True)
    safe_top_k = max(1, request.top_k)
    top_results = scored_results[:safe_top_k]

    return SearchResponse(
        query=request.query,
        total_results=len(top_results),
        results=top_results,
    )
