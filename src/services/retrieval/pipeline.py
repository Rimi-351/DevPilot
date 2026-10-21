"""Multi-mode retrieval pipeline supporting vector_only, hybrid (Dense+BM25 with RRF), and hybrid_rerank."""

from __future__ import annotations

import math
from typing import Any

from src.services.embedding import get_embedding_service
from src.services.retrieval.hybrid import bm25_search, reciprocal_rank_fusion
from src.services.retrieval.reranker import get_reranker_service


def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    if not vec1 or not vec2:
        return 0.0

    length = min(len(vec1), len(vec2))
    if length == 0:
        return 0.0

    dot_product = sum(vec1[i] * vec2[i] for i in range(length))
    norm1 = math.sqrt(sum(x * x for x in vec1[:length]))
    norm2 = math.sqrt(sum(y * y for y in vec2[:length]))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    similarity = dot_product / (norm1 * norm2)
    return float(max(-1.0, min(1.0, similarity)))


async def retrieve_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    search_mode: str = "vector_only",
    top_k: int = 3,
    chunk_limit: int = 10,
    query_vector: list[float] | None = None,
    reranker: Any | None = None,
) -> list[dict[str, Any]]:
    """Retrieve and rank document chunks using the specified search mode.

    Modes supported:
        - "vector_only": Dense embedding cosine similarity ranking.
        - "hybrid": Dense + BM25 sparse search merged via Reciprocal Rank Fusion (RRF).
        - "hybrid_rerank": Dense + BM25 (RRF candidates) re-scored with Cross-Encoder reranker.

    Args:
        query: Query string.
        chunks: List of candidate chunk dictionaries.
        search_mode: "vector_only", "hybrid", or "hybrid_rerank".
        top_k: Final number of ranked chunks to return.
        chunk_limit: Candidate pool size for initial retrieval before fusion/reranking.
        query_vector: Optional precomputed query embedding vector.

    Returns:
        Ranked list of chunk dictionaries trimmed to top_k.
    """
    if not chunks or top_k <= 0:
        return []

    # Empty or whitespace query guard
    if not query or not query.strip():
        return [dict(c, score=0.0) for c in chunks[:top_k]]

    safe_chunk_limit = max(1, chunk_limit)

    # 1. Compute Dense Vector Rankings
    dense_scored = []
    if query_vector is None:
        embedding_service = get_embedding_service()
        query_vector = await embedding_service.generate_query_embedding(query)

    for c in chunks:
        chunk_emb = c.get("embedding") or []
        sim = compute_cosine_similarity(query_vector, chunk_emb) if query_vector else 0.0
        item = dict(c)
        item["score"] = sim
        dense_scored.append(item)

    dense_scored.sort(key=lambda x: x["score"], reverse=True)

    # Fast path: vector_only mode
    if search_mode == "vector_only":
        return dense_scored[:top_k]

    # 2. Compute BM25 Sparse Rankings
    sparse_candidates = bm25_search(query, chunks, top_k=safe_chunk_limit)

    # 3. Fuse via Reciprocal Rank Fusion (RRF)
    dense_candidates = dense_scored[:safe_chunk_limit]
    rrf_top_n = max(safe_chunk_limit, 10) if search_mode == "hybrid_rerank" else top_k
    fused_candidates = reciprocal_rank_fusion(
        dense_results=dense_candidates,
        sparse_results=sparse_candidates,
        k=60,
        top_n=rrf_top_n,
    )

    if search_mode == "hybrid":
        return fused_candidates[:top_k]

    # 4. Cross-Encoder Reranking
    if search_mode == "hybrid_rerank":
        active_reranker = reranker if reranker is not None else get_reranker_service()
        reranked = active_reranker.rerank(query, fused_candidates, top_k=top_k)
        return reranked

    # Fallback to dense if unknown mode
    return dense_scored[:top_k]

