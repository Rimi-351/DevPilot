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


def test_tokenize_multilingual_bangla_and_banglish():
    # 1. Pure Bangla script with combining vowel diacritics
    bangla_text = "আমি বাংলায় গান গাই। DevPilot-এ দ্রুত কোড সার্চ করুন!"
    bn_tokens = tokenize(bangla_text)
    assert "আমি" in bn_tokens
    assert "গান" in bn_tokens
    assert "গাই" in bn_tokens
    assert "devpilot" in bn_tokens
    assert "দ্রুত" in bn_tokens
    assert "সার্চ" in bn_tokens
    assert "করুন" in bn_tokens

    # 2. Romanized code-mixed Banglish
    banglish_text = "DevPilot ekta modern AI assistant, khub fast search kore!"
    bng_tokens = tokenize(banglish_text)
    assert "devpilot" in bng_tokens
    assert "ekta" in bng_tokens
    assert "modern" in bng_tokens
    assert "ai" in bng_tokens
    assert "assistant" in bng_tokens
    assert "khub" in bng_tokens
    assert "fast" in bng_tokens
    assert "search" in bng_tokens
    assert "kore" in bng_tokens

    # 3. Alphanumeric code-mixed text
    mixed_text = "API endpoint-e error 500 ashche, chunk_id_01 check korun."
    mixed_tokens = tokenize(mixed_text)
    assert "500" in mixed_tokens
    assert "endpoint" in mixed_tokens
    assert "error" in mixed_tokens
    assert "chunk_id_01" in mixed_tokens
    assert "korun" in mixed_tokens


def test_bm25_multilingual_search():
    corpus = [
        {"chunk_id": "bn_chunk", "content": "DevPilot একটি আধুনিক এআই চালিত কোডিং অ্যাসিস্ট্যান্ট যা ডেভেলপারদের সাহায্য করে।"},
        {"chunk_id": "bng_chunk", "content": "DevPilot ekta modern AI coding assistant ja developers der sahajjo kore."},
        {"chunk_id": "en_chunk", "content": "DevPilot is a modern AI coding assistant that helps software developers."},
    ]
    # Bangla search
    bn_results = bm25_search("কোডিং অ্যাসিস্ট্যান্ট সাহায্য", corpus, top_k=1)
    assert len(bn_results) == 1
    assert bn_results[0]["chunk_id"] == "bn_chunk"

    # Banglish search
    bng_results = bm25_search("developers der sahajjo kore", corpus, top_k=1)
    assert len(bng_results) == 1
    assert bng_results[0]["chunk_id"] == "bng_chunk"


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


@pytest.mark.asyncio
async def test_multilingual_embedding_service():
    from src.services.embedding import get_embedding_service

    svc = get_embedding_service()
    assert svc.dimensions == 384

    texts = [
        "DevPilot FastEmbed and SentenceTransformers multilingual support",
        "DevPilot একটি আধুনিক এআই চালিত কোডিং অ্যাসিস্ট্যান্ট যা ডেভেলপারদের সাহায্য করে।",
        "DevPilot ekta modern AI coding assistant ja developers der sahajjo kore.",
    ]
    embeddings = await svc.generate_embeddings(texts)
    assert len(embeddings) == 3
    for emb in embeddings:
        assert len(emb) == 384
        # Verify L2 normalization
        norm = sum(x * x for x in emb) ** 0.5
        assert 0.99 <= norm <= 1.01

    # Semantic relevance check for Bangla
    doc_bn = "ডাটাবেস মাইগ্রেশনের জন্য আমরা Alembic এবং PostgreSQL ব্যবহার করি।"
    q_bn_rel = "Alembic এবং ডাটাবেস মাইগ্রেশন কিভাবে কাজ করে?"
    q_bn_irrel = "আজকের আবহাওয়া কেমন এবং বৃষ্টি হবে কি না?"

    emb_doc = await svc.generate_query_embedding(doc_bn)
    emb_rel = await svc.generate_query_embedding(q_bn_rel)
    emb_irrel = await svc.generate_query_embedding(q_bn_irrel)

    sim_rel = sum(a * b for a, b in zip(emb_doc, emb_rel))
    sim_irrel = sum(a * b for a, b in zip(emb_doc, emb_irrel))
    assert sim_rel > sim_irrel


def test_multilingual_gold_100_dataset_schema_and_distribution():
    from pathlib import Path
    import json

    gold_path = Path(__file__).resolve().parents[1] / "benchmarks" / "multilingual_gold_100.jsonl"
    assert gold_path.exists(), "benchmarks/multilingual_gold_100.jsonl must exist"

    with open(gold_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    assert len(records) == 100, f"Expected 100 queries, found {len(records)}"

    lang_counts = {}
    required_keys = {"query_id", "language", "query", "ground_truth_chunk_ids", "reference_answer"}

    for r in records:
        assert required_keys.issubset(r.keys()), f"Missing keys in record {r.get('query_id')}"
        lang = r["language"]
        assert lang in ("english", "bangla", "banglish")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        assert len(r["query"]) > 5
        assert len(r["ground_truth_chunk_ids"]) >= 1
        assert len(r["reference_answer"]) > 5

    assert lang_counts["english"] == 34
    assert lang_counts["bangla"] == 33
    assert lang_counts["banglish"] == 33

