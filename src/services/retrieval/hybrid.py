"""Hybrid search implementation combining dense vector retrieval and BM25 sparse search with Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

import re
from typing import Any

from rank_bm25 import BM25Okapi

# Multilingual Unicode token pattern supporting English, Bangla script (\u0980-\u09ff),
# Zero-width joiner/non-joiner (\u200c, \u200d), and code-mixed Latin Banglish tokens.
_MULTILINGUAL_TOKEN_PATTERN = re.compile(r"[\w\u0980-\u09ff\u200c\u200d]+")


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric and multilingual tokens.

    Correctly handles Unicode word boundaries for Bangla script, combining vowel marks,
    alphanumeric code-mixed Banglish, and English.
    """
    if not text:
        return []
    return _MULTILINGUAL_TOKEN_PATTERN.findall(text.lower())


# In-memory index cache for BM25: cache_key -> (corpus_length, bm25_instance, corpus_chunks)
_bm25_cache: dict[str, tuple[int, BM25Okapi, list[dict[str, Any]]]] = {}


def _get_corpus_cache_key(corpus_chunks: list[dict[str, Any]]) -> str:
    """Derive a stable cache key from project_id or chunk content hashes."""
    if not corpus_chunks:
        return "empty"
    project_id = corpus_chunks[0].get("project_id")
    if project_id:
        return f"proj_{project_id}"

    chunk_identifiers = tuple(
        str(c.get("chunk_id") or c.get("id") or hash(c.get("content", "")))
        for c in corpus_chunks
    )
    return f"corpus_{hash(chunk_identifiers)}"


def get_or_create_bm25_index(
    corpus_chunks: list[dict[str, Any]],
) -> tuple[BM25Okapi, list[dict[str, Any]]]:
    """Retrieve cached BM25Okapi instance or build and cache a new one if corpus changed."""
    cache_key = _get_corpus_cache_key(corpus_chunks)
    corpus_len = len(corpus_chunks)

    if cache_key in _bm25_cache:
        cached_len, cached_bm25, cached_chunks = _bm25_cache[cache_key]
        if cached_len == corpus_len:
            return cached_bm25, cached_chunks

    tokenized_corpus = [tokenize(c.get("content", "")) for c in corpus_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    _bm25_cache[cache_key] = (corpus_len, bm25, corpus_chunks)
    return bm25, corpus_chunks


def clear_bm25_cache() -> None:
    """Clear the in-memory BM25 index cache."""
    _bm25_cache.clear()



def bm25_search(
    query: str,
    corpus_chunks: list[dict[str, Any]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Perform BM25 sparse search over a collection of candidate document chunks.

    Args:
        query: User search or question string.
        corpus_chunks: List of dictionaries containing at least 'content' and an identifier ('chunk_id' or 'id').
        top_k: Maximum number of sparse search results to return.

    Returns:
        List of chunks sorted by descending BM25 score with 'bm25_score' attached.
    """
    if not corpus_chunks:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        # If query has no tokens, return first top_k chunks with score 0.0
        results = []
        for c in corpus_chunks[:top_k]:
            item = dict(c)
            item["bm25_score"] = 0.0
            results.append(item)
        return results

    bm25, indexed_chunks = get_or_create_bm25_index(corpus_chunks)
    scores = bm25.get_scores(query_tokens)

    scored_chunks = []
    for chunk, score in zip(indexed_chunks, scores):
        item = dict(chunk)
        item["bm25_score"] = float(score)
        scored_chunks.append(item)

    scored_chunks.sort(key=lambda x: x["bm25_score"], reverse=True)
    return scored_chunks[:top_k]


def reciprocal_rank_fusion(
    dense_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    k: int = 60,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Fuse dense vector and sparse lexical retrieval rankings using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF_Score(d) = sum(1 / (k + rank + 1))
    where rank is the 0-indexed rank of document d in each respective candidate list.

    Args:
        dense_results: Candidate chunks ranked by dense vector similarity.
        sparse_results: Candidate chunks ranked by sparse lexical similarity (e.g. BM25).
        k: Smoothing constant parameter (standard default is 60).
        top_n: Number of fused results to return.

    Returns:
        List of fused, deduplicated candidate chunks sorted by descending RRF score.
    """
    rrf_scores: dict[str, float] = {}
    doc_lookup: dict[str, dict[str, Any]] = {}

    def get_doc_id(doc: dict[str, Any]) -> str:
        # Unique identifier fallback chain
        if "chunk_id" in doc and doc["chunk_id"] is not None:
            return str(doc["chunk_id"])
        if "id" in doc and doc["id"] is not None:
            return str(doc["id"])
        # Fallback to content hash or content slice
        return str(hash(doc.get("content", "")))

    # 1. Accumulate RRF scores from dense candidates
    for rank, doc in enumerate(dense_results):
        doc_id = get_doc_id(doc)
        score = 1.0 / (k + rank + 1)
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + score
        if doc_id not in doc_lookup:
            doc_lookup[doc_id] = dict(doc)

    # 2. Accumulate RRF scores from sparse candidates
    for rank, doc in enumerate(sparse_results):
        doc_id = get_doc_id(doc)
        score = 1.0 / (k + rank + 1)
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + score
        if doc_id not in doc_lookup:
            doc_lookup[doc_id] = dict(doc)

    # 3. Sort merged candidates by descending RRF score
    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda d_id: rrf_scores[d_id], reverse=True)

    fused_results: list[dict[str, Any]] = []
    for doc_id in sorted_doc_ids[:top_n]:
        doc = dict(doc_lookup[doc_id])
        doc["rrf_score"] = float(rrf_scores[doc_id])
        fused_results.append(doc)

    return fused_results
