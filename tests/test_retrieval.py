"""Unit and integration tests for Week 5 Hybrid Search, BM25, RRF, Cross-Encoder Reranker, and Benchmark Runner."""

import json
from pathlib import Path
import pytest

from src.services.retrieval.hybrid import bm25_search, reciprocal_rank_fusion, tokenize
from src.services.retrieval.reranker import RerankerService
from src.services.retrieval.pipeline import retrieve_chunks
from src.evaluation.runner import (
    load_benchmark_dataset,
    evaluate_mode,
    check_unsupported_claims,
    compute_percentile,
)


def test_tokenize():
    text = "FastAPI 0.115+ & SQLAlchemy 2.0 with PostgreSQL!"
    tokens = tokenize(text)
    assert "fastapi" in tokens
    assert "sqlalchemy" in tokens
    assert "postgresql" in tokens
    assert "0" in tokens
    assert "115" in tokens


def test_bm25_search_ranking():
    corpus = [
        {"chunk_id": "c1", "content": "PostgreSQL database migrations using Alembic schema evolution."},
        {"chunk_id": "c2", "content": "FastAPI web framework with async route handlers and Pydantic."},
        {"chunk_id": "c3", "content": "Alembic auto-generates migration scripts from SQLAlchemy metadata."},
    ]
    results = bm25_search("Alembic migrations", corpus, top_k=2)
    assert len(results) == 2
    # Top results should be c1 or c3 which mention Alembic & migrations
    retrieved_ids = [r["chunk_id"] for r in results]
    assert "c1" in retrieved_ids or "c3" in retrieved_ids
    assert results[0]["bm25_score"] >= results[1]["bm25_score"]


def test_reciprocal_rank_fusion_formula():
    dense = [
        {"chunk_id": "doc_a", "content": "Document A"},
        {"chunk_id": "doc_b", "content": "Document B"},
        {"chunk_id": "doc_c", "content": "Document C"},
    ]
    sparse = [
        {"chunk_id": "doc_b", "content": "Document B"},
        {"chunk_id": "doc_d", "content": "Document D"},
        {"chunk_id": "doc_a", "content": "Document A"},
    ]

    # k=60
    # doc_a: rank 0 in dense (1/(60+0+1) = 1/61) + rank 2 in sparse (1/(60+2+1) = 1/63)
    # doc_b: rank 1 in dense (1/(60+1+1) = 1/62) + rank 0 in sparse (1/(60+0+1) = 1/61)
    fused = reciprocal_rank_fusion(dense, sparse, k=60, top_n=3)
    assert len(fused) == 3
    # doc_b has 1/62 + 1/61 = 0.016129 + 0.016393 = 0.032522
    # doc_a has 1/61 + 1/63 = 0.016393 + 0.015873 = 0.032266
    # doc_b should rank first!
    assert fused[0]["chunk_id"] == "doc_b"
    assert fused[1]["chunk_id"] == "doc_a"
    assert "rrf_score" in fused[0]
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]


def test_reranker_service_ordering():
    reranker = RerankerService(force_fallback=True)
    candidates = [
        {"chunk_id": "c1", "content": "Unrelated fruit and apples in the basket."},
        {"chunk_id": "c2", "content": "PostgreSQL database migrations with Alembic."},
    ]
    query = "How to run database migrations?"
    reranked = reranker.rerank(query, candidates, top_k=2)
    assert len(reranked) == 2
    # c2 has words 'database' and 'migrations', so heuristic score should be higher
    assert reranked[0]["chunk_id"] == "c2"
    assert "rerank_score" in reranked[0]
    assert reranked[0]["reranker_applied"] is True
    assert reranked[0]["reranker_engine"] == "heuristic"


@pytest.mark.asyncio
async def test_retrieve_chunks_all_modes():
    corpus = [
        {"chunk_id": "c1", "content": "Alembic migrations in DevPilot", "embedding": [1.0, 0.0]},
        {"chunk_id": "c2", "content": "FastAPI async endpoints", "embedding": [0.0, 1.0]},
    ]
    query = "Alembic migrations"

    # vector_only
    v_results = await retrieve_chunks(query, corpus, search_mode="vector_only", top_k=1)
    assert len(v_results) == 1

    # hybrid
    h_results = await retrieve_chunks(query, corpus, search_mode="hybrid", top_k=1)
    assert len(h_results) == 1
    assert "rrf_score" in h_results[0]

    # hybrid_rerank
    hr_results = await retrieve_chunks(query, corpus, search_mode="hybrid_rerank", top_k=1)
    assert len(hr_results) == 1
    assert "rerank_score" in hr_results[0]
    assert hr_results[0]["reranker_applied"] is True


def test_unsupported_claims_metric():
    retrieved = [{"index": 1, "content": "DevPilot uses Alembic for database migrations and schema evolution."}]
    grounded_answer = "DevPilot uses Alembic for database migrations [1]."
    hallucinated_answer = "DevPilot uses MongoDB Atlas cloud clusters for serverless scaling [1]."

    rate_grounded = check_unsupported_claims(grounded_answer, retrieved)
    rate_hallucinated = check_unsupported_claims(hallucinated_answer, retrieved)

    assert rate_grounded == 0.0
    assert rate_hallucinated == 1.0


def test_compute_percentiles():
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p50 = compute_percentile(latencies, 50)
    p95 = compute_percentile(latencies, 95)
    assert p50 == 60.0
    assert p95 == 100.0


def test_bm25_index_cache():
    from src.services.retrieval.hybrid import clear_bm25_cache, get_or_create_bm25_index

    clear_bm25_cache()
    corpus = [
        {"chunk_id": "c1", "content": "Sample content one", "project_id": "proj-123"},
        {"chunk_id": "c2", "content": "Sample content two", "project_id": "proj-123"},
    ]

    index1, chunks1 = get_or_create_bm25_index(corpus)
    index2, chunks2 = get_or_create_bm25_index(corpus)

    # Must be the exact same cached instance in memory
    assert index1 is index2

    # If corpus changes (e.g. new chunk added), cache rebuilds
    corpus_expanded = corpus + [{"chunk_id": "c3", "content": "Sample three", "project_id": "proj-123"}]
    index3, chunks3 = get_or_create_bm25_index(corpus_expanded)
    assert index3 is not index1

