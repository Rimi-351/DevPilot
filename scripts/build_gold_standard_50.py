"""Script to build benchmarks/gold_standard_50.jsonl with 50 diverse queries and rich technical corpus."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.embedding import get_embedding_service

# Define reusable corpus chunks
CHUNKS_POOL = {
    "chunk_config_01": {
        "chunk_id": "chunk_config_01",
        "content": "Settings specification: CHUNK_SIZE is defaulted to 512 characters and CHUNK_OVERLAP is defaulted to 64 characters in src/core/config.py to standardize text chunking across DevPilot.",
        "filename": "config.md",
    },
    "chunk_security_01": {
        "chunk_id": "chunk_security_01",
        "content": "Security dependencies in src/core/security.py extract the X-API-Key header, raising HTTP 401 Unauthorized if missing, empty, or whitespace to authenticate API callers.",
        "filename": "security.md",
    },
    "chunk_rrf_01": {
        "chunk_id": "chunk_rrf_01",
        "content": "Reciprocal Rank Fusion uses constant k=60 to balance dense and BM25 rank contributions: RRF_score = sum(1.0 / (60 + rank + 1)), ensuring high-confidence matches in either mode rank near the top.",
        "filename": "retrieval_fusion.md",
    },
    "chunk_bm25_01": {
        "chunk_id": "chunk_bm25_01",
        "content": "Sparse search utilizes BM25Okapi from the rank-bm25 package to tokenize and score document terms with term frequency and inverse document frequency statistics.",
        "filename": "bm25_search.md",
    },
    "chunk_embedding_01": {
        "chunk_id": "chunk_embedding_01",
        "content": "DevPilot FastEmbed service uses model BAAI/bge-small-en-v1.5 producing 384-dimensional dense vectors on ONNX Runtime for fast vector similarity search.",
        "filename": "embedding_spec.md",
    },
    "chunk_reranker_01": {
        "chunk_id": "chunk_reranker_01",
        "content": "The Cross-Encoder Reranker uses cross-encoder/ms-marco-MiniLM-L-6-v2 to evaluate full query-document interaction across top candidates, assigning rerank_score to each item.",
        "filename": "reranker_spec.md",
    },
    "chunk_rerank_fallback_01": {
        "chunk_id": "chunk_rerank_fallback_01",
        "content": "When transformer models fail to load or are unavailable, RerankerService logs warning 'RERANKER_FALLBACK_ACTIVE' and applies lexical term overlap heuristics with reranker_engine metadata.",
        "filename": "reranker_fallback.md",
    },
    "chunk_unsupported_claims_01": {
        "chunk_id": "chunk_unsupported_claims_01",
        "content": "The unsupported_claims_rate metric defines a threshold of 0.40 sentence-to-chunk token overlap ratio, flagging sentences below 40% overlap as ungrounded or hallucinated.",
        "filename": "metrics_spec.md",
    },
    "chunk_storage_01": {
        "chunk_id": "chunk_storage_01",
        "content": "LocalStorageService restricts uploaded files to a maximum size of 10MB (10485760 bytes), rejecting larger files with HTTP 413 and persisting accepted files organized by project ID.",
        "filename": "storage_service.md",
    },
    "chunk_job_status_01": {
        "chunk_id": "chunk_job_status_01",
        "content": "ProcessingJob status transitions through JobStatus enum: PENDING, IN_PROGRESS, COMPLETED, and FAILED, allowing clients to poll job progress asynchronously.",
        "filename": "jobs_status.md",
    },
    "chunk_alembic_01": {
        "chunk_id": "chunk_alembic_01",
        "content": "Database migrations manage PostgreSQL schema evolution using command 'alembic upgrade head' to apply migrations auto-generated from SQLAlchemy 2.0 declarative models.",
        "filename": "alembic_migrations.md",
    },
    "chunk_tenant_403_01": {
        "chunk_id": "chunk_tenant_403_01",
        "content": "Cross-tenant project access triggers verify_project_tenant_access and returns HTTP 403 Forbidden whenever an authenticated caller attempts accessing or modifying another tenant's project.",
        "filename": "multitenancy_isolation.md",
    },
    "chunk_storage_hash_01": {
        "chunk_id": "chunk_storage_hash_01",
        "content": "LocalStorageService computes a hexadecimal SHA-256 digest over file bytes for content verification and duplicate detection before saving raw bytes to disk.",
        "filename": "storage_hash.md",
    },
    "chunk_background_01": {
        "chunk_id": "chunk_background_01",
        "content": "Document ingestion runs asynchronously via FastAPI BackgroundTasks with an independent async_session_factory DB session, updating ProcessingJob state without blocking requests.",
        "filename": "background_tasks.md",
    },
    "chunk_db_drivers_01": {
        "chunk_id": "chunk_db_drivers_01",
        "content": "DevPilot uses asyncpg for PostgreSQL connections in production and aiosqlite for in-memory SQLite automated test runs, utilizing SQLAlchemy async_sessionmaker.",
        "filename": "database_engine.md",
    },
    "chunk_multitenancy_01": {
        "chunk_id": "chunk_multitenancy_01",
        "content": "Multi-tenant project isolation partitions every document chunk strictly by project_id foreign keys and tenant ownership columns, preventing data leakage across tenant boundaries during semantic queries.",
        "filename": "tenant_partitioning.md",
    },
    "chunk_rag_grounding_01": {
        "chunk_id": "chunk_rag_grounding_01",
        "content": "RAG answer generation enforces strict context grounding: every claim must cite source excerpts with markers like [1], and queries lacking matching excerpts receive negative rejection.",
        "filename": "rag_grounding.md",
    },
    "chunk_storage_path_01": {
        "chunk_id": "chunk_storage_path_01",
        "content": "Uploaded source files are persisted locally in the configured storage directory structure under projects/{project_id}/files/ with unique sanitized filenames.",
        "filename": "storage_path.md",
    },
    "chunk_chunking_sliding_01": {
        "chunk_id": "chunk_chunking_sliding_01",
        "content": "Sliding-window text segmentation advances by chunk_size minus chunk_overlap, preserving contextual continuity across chunk boundaries so sentences split across windows are still retrievable.",
        "filename": "sliding_window.md",
    },
    "chunk_bm25_cache_01": {
        "chunk_id": "chunk_bm25_cache_01",
        "content": "BM25 index caching maintains pre-tokenized BM25Okapi instances in an in-memory LRU cache keyed by project ID and corpus hash, eliminating redundant tokenization overhead.",
        "filename": "bm25_cache.md",
    },
    "chunk_citation_offsets_01": {
        "chunk_id": "chunk_citation_offsets_01",
        "content": "Citations returned by RAG endpoints record start_offset and end_offset character positions in the parent document, providing exact provenance for every cited fact.",
        "filename": "citation_offsets.md",
    },
    "chunk_session_factory_01": {
        "chunk_id": "chunk_session_factory_01",
        "content": "FastAPI request handlers receive an AsyncSession via get_db dependency, while background workers construct a fresh session via async_session_factory to avoid session lifetime conflicts.",
        "filename": "db_sessions.md",
    },
    "chunk_search_404_01": {
        "chunk_id": "chunk_search_404_01",
        "content": "Searching against a non-existent project UUID raises HTTP 404 Not Found before any embedding generation or database chunk querying begins.",
        "filename": "search_errors.md",
    },
    "chunk_latency_percentiles_01": {
        "chunk_id": "chunk_latency_percentiles_01",
        "content": "BenchmarkRunner records retrieval and answer synthesis durations, computing P50 median latency and P95 tail latency percentiles across evaluation runs.",
        "filename": "latency_metrics.md",
    },
    "chunk_extractor_formats_01": {
        "chunk_id": "chunk_extractor_formats_01",
        "content": "Text extraction supports PDF documents via PyPDF, markdown (.md), plain text (.txt), and Python source (.py) files, decoding UTF-8 character streams.",
        "filename": "extractor_formats.md",
    },
    "chunk_negative_response_01": {
        "chunk_id": "chunk_negative_response_01",
        "content": "When no retrieved chunks contain relevant keywords or high semantic similarity, the LLM service returns NEGATIVE_RESPONSE: 'I do not have enough information in the provided documents to answer this question.'",
        "filename": "negative_response.md",
    },
    "chunk_benchmark_metrics_01": {
        "chunk_id": "chunk_benchmark_metrics_01",
        "content": "IR benchmark evaluation computes Hit@k (proportion of queries where ground truth appears in top k items) and Mean Reciprocal Rank (MRR) measuring rank position quality.",
        "filename": "benchmark_metrics.md",
    },
}

# Distractor chunks to populate corpus pools
DISTRACTORS = [
    CHUNKS_POOL["chunk_docker_01"] if "chunk_docker_01" in CHUNKS_POOL else {
        "chunk_id": "distractor_docker",
        "content": "Docker Compose runs the local PostgreSQL service on port 5432 with healthchecks and persistent volumes.",
        "filename": "docker.md",
    },
    {
        "chunk_id": "distractor_cors",
        "content": "FastAPI CORS middleware allows cross-origin requests from frontend localhost origins in development.",
        "filename": "cors.md",
    },
    {
        "chunk_id": "distractor_logging",
        "content": "Structured JSON logging records request timestamps, HTTP methods, route paths, and response status codes.",
        "filename": "logging.md",
    },
    {
        "chunk_id": "distractor_health",
        "content": "Health endpoints /health and / return application name, version, and database connectivity status.",
        "filename": "health.md",
    },
]

# Definition of the 50 queries: (query, ground_truth_chunk_keys, reference_answer, category)
RAW_QUERIES = [
    # ── Category 1: Exact Keyword Matches & Code Identifiers (1-15) ───────────
    (
        "What are the default values of CHUNK_SIZE and CHUNK_OVERLAP in DevPilot configuration?",
        ["chunk_config_01"],
        "CHUNK_SIZE defaults to 512 and CHUNK_OVERLAP defaults to 64 in src/core/config.py.",
    ),
    (
        "How is X-API-Key header validated for incoming requests?",
        ["chunk_security_01"],
        "The X-API-Key header is validated by get_current_api_key in src/core/security.py, returning 401 if missing or empty.",
    ),
    (
        "What value of k is used in reciprocal_rank_fusion formula in DevPilot?",
        ["chunk_rrf_01"],
        "Reciprocal Rank Fusion uses constant k=60 to fuse dense and sparse ranks.",
    ),
    (
        "Which BM25 implementation class is utilized for sparse keyword retrieval?",
        ["chunk_bm25_01"],
        "DevPilot utilizes BM25Okapi from the rank-bm25 package.",
    ),
    (
        "What vector dimension and dense embedding model are used in FastEmbed?",
        ["chunk_embedding_01"],
        "FastEmbed uses BAAI/bge-small-en-v1.5 producing 384-dimensional dense vectors.",
    ),
    (
        "What cross-encoder model checkpoint is deployed for candidate reranking?",
        ["chunk_reranker_01"],
        "DevPilot uses cross-encoder/ms-marco-MiniLM-L-6-v2 for candidate reranking.",
    ),
    (
        "What log warning is emitted when cross-encoder reranking falls back to heuristic scoring?",
        ["chunk_rerank_fallback_01"],
        "When reranker falls back, it logs 'RERANKER_FALLBACK_ACTIVE' and uses term overlap heuristics.",
    ),
    (
        "What token overlap threshold is required to classify a claim as supported?",
        ["chunk_unsupported_claims_01"],
        "The unsupported claims rate threshold is 0.40 sentence-to-chunk token overlap ratio.",
    ),
    (
        "How does LocalStorageService enforce max file upload size and what is the limit?",
        ["chunk_storage_01"],
        "LocalStorageService enforces a 10MB (10,485,760 bytes) limit, returning HTTP 413 for oversized files.",
    ),
    (
        "What are the valid lifecycle status values of a ProcessingJob in DevPilot?",
        ["chunk_job_status_01"],
        "Valid ProcessingJob statuses are PENDING, IN_PROGRESS, COMPLETED, and FAILED.",
    ),
    (
        "Which database migration command upgrades schema to the latest version with Alembic?",
        ["chunk_alembic_01"],
        "Alembic upgrades the schema using the command 'alembic upgrade head'.",
    ),
    (
        "What error status code is returned when a caller accesses a project belonging to another tenant?",
        ["chunk_tenant_403_01"],
        "Cross-tenant access triggers verify_project_tenant_access and returns HTTP 403 Forbidden.",
    ),
    (
        "What hashing algorithm is used by LocalStorageService for deduplication and content hashing?",
        ["chunk_storage_hash_01"],
        "LocalStorageService computes a hexadecimal SHA-256 digest over file content.",
    ),
    (
        "What background execution mechanism runs text extraction without blocking the request loop?",
        ["chunk_background_01"],
        "Document ingestion executes asynchronously using FastAPI BackgroundTasks with an independent DB session.",
    ),
    (
        "Which async database driver is configured for PostgreSQL and SQLite in DevPilot?",
        ["chunk_db_drivers_01"],
        "DevPilot uses asyncpg for PostgreSQL and aiosqlite for in-memory SQLite.",
    ),

    # ── Category 2: Paraphrased Questions & Conceptual Understanding (16-30) ──
    (
        "How does DevPilot ensure that multiple organizations cannot view each other's documents?",
        ["chunk_multitenancy_01"],
        "Multi-tenant isolation partitions document chunks strictly by project_id and tenant ownership columns.",
    ),
    (
        "What mechanism blends dense neural vector similarity with sparse lexical keyword scores?",
        ["chunk_rrf_01"],
        "Reciprocal Rank Fusion (RRF) merges dense vector rankings and BM25 sparse rankings.",
    ),
    (
        "How does the system prevent the language model from generating hallucinated statements?",
        ["chunk_rag_grounding_01"],
        "RAG enforces strict context grounding, requiring factual claims to cite context excerpts with markers like [1].",
    ),
    (
        "Where are binary document uploads stored on the local file system?",
        ["chunk_storage_path_01"],
        "Uploaded source files are persisted under projects/{project_id}/files/ on disk.",
    ),
    (
        "How does the text segmentation process avoid losing context between adjacent passages?",
        ["chunk_chunking_sliding_01"],
        "Sliding-window text segmentation advances by chunk_size minus chunk_overlap, preserving contextual continuity.",
    ),
    (
        "What secondary ranking step re-evaluates top retrieval candidates using deep cross-attention?",
        ["chunk_reranker_01"],
        "A Cross-Encoder Reranker re-scores top candidates by evaluating full query-document interaction.",
    ),
    (
        "How does the retrieval engine avoid re-tokenizing the entire corpus on every user search?",
        ["chunk_bm25_cache_01"],
        "BM25 index caching stores pre-tokenized BM25Okapi instances in an in-memory cache keyed by corpus hash.",
    ),
    (
        "What happens if the cross-encoder transformer fails to load or runs out of GPU memory?",
        ["chunk_rerank_fallback_01"],
        "The system activates a heuristic fallback based on lexical term overlap and logs RERANKER_FALLBACK_ACTIVE.",
    ),
    (
        "How are citation markers linked to specific source chunk character offsets?",
        ["chunk_citation_offsets_01"],
        "Citations include start_offset and end_offset character boundaries pointing to the original document text.",
    ),
    (
        "What header credential must clients provide to authenticate their API calls?",
        ["chunk_security_01"],
        "API clients must supply an X-API-Key header to authenticate incoming requests.",
    ),
    (
        "How is database session isolation maintained between API endpoints and async background tasks?",
        ["chunk_session_factory_01"],
        "FastAPI routes use get_db while background workers create fresh sessions via async_session_factory.",
    ),
    (
        "What happens if an API client submits a search request for a project that does not exist?",
        ["chunk_search_404_01"],
        "The search endpoint validates project existence and returns HTTP 404 Not Found if missing.",
    ),
    (
        "How does DevPilot benchmark runner compute P50 and P95 latency percentiles?",
        ["chunk_latency_percentiles_01"],
        "BenchmarkRunner tracks retrieval and generation durations, computing 50th and 95th percentile latencies.",
    ),
    (
        "What file formats can be uploaded and processed into searchable vector chunks?",
        ["chunk_extractor_formats_01"],
        "DevPilot supports PDF, markdown (.md), text (.txt), and Python source code (.py).",
    ),
    (
        "How does the system handle documents when no search terms match any chunks?",
        ["chunk_negative_response_01"],
        "When no chunks match, the system returns NEGATIVE_RESPONSE stating lack of information.",
    ),

    # ── Category 3: Multi-Chunk Synthesis Queries (31-40) ─────────────────────
    (
        "How do document chunking parameters and embedding dimensions together configure the vector representation pipeline?",
        ["chunk_config_01", "chunk_embedding_01"],
        "Text is segmented into 512-character chunks with 64-character overlap, then transformed into 384-dimensional dense vectors by FastEmbed.",
    ),
    (
        "Describe how authentication headers and database tenant columns enforce multi-tenant isolation.",
        ["chunk_security_01", "chunk_tenant_403_01"],
        "The X-API-Key header identifies the caller, and verify_project_tenant_access checks that against project tenant columns, returning 403 on mismatch.",
    ),
    (
        "How do BM25 index caching and Reciprocal Rank Fusion interact during hybrid search execution?",
        ["chunk_bm25_cache_01", "chunk_rrf_01"],
        "BM25 index caching avoids redundant tokenization, and reciprocal rank fusion fuses sparse BM25 scores with dense similarity using k=60.",
    ),
    (
        "Describe the lifecycle of an uploaded document from local disk persistence to background chunk creation.",
        ["chunk_storage_01", "chunk_background_01"],
        "LocalStorageService validates size and saves the file, then FastAPI BackgroundTasks asynchronously extracts text, chunks, and persists embeddings.",
    ),
    (
        "How do the cross-encoder reranker and heuristic fallback ensure search resilience and transparency?",
        ["chunk_reranker_01", "chunk_rerank_fallback_01"],
        "The system attempts cross-encoder reranking and falls back to term overlap heuristic if unavailable, logging RERANKER_FALLBACK_ACTIVE.",
    ),
    (
        "What is the relationship between citation provenance markers in RAG answers and source document character offsets?",
        ["chunk_citation_offsets_01", "chunk_rag_grounding_01"],
        "RAG answers include citation markers like [1], which map to citations containing start_offset and end_offset in the source file.",
    ),
    (
        "How do Alembic migrations and PostgreSQL connection settings maintain database schema integrity?",
        ["chunk_alembic_01", "chunk_db_drivers_01"],
        "Alembic manages schema evolution with upgrade head while asyncpg connects to PostgreSQL with connection pooling.",
    ),
    (
        "How do sentence token overlap threshold and citation checks compute the unsupported claims rate?",
        ["chunk_unsupported_claims_01", "chunk_rag_grounding_01"],
        "Unsupported claims rate evaluates whether generated claim sentences cite chunks with at least 0.40 token overlap, flagging ungrounded claims.",
    ),
    (
        "What are the roles of FastAPI route dependencies and SQLAlchemy async sessions in tenant project validation?",
        ["chunk_security_01", "chunk_session_factory_01"],
        "FastAPI dependencies inject validated API keys and async database sessions to look up projects and verify tenant ownership.",
    ),
    (
        "How do P50 and P95 percentiles together with Hit@k evaluate overall retrieval and generation quality?",
        ["chunk_latency_percentiles_01", "chunk_benchmark_metrics_01"],
        "Hit@k and MRR evaluate retrieval relevance, while P50 and P95 latency percentiles measure system throughput and responsiveness.",
    ),

    # ── Category 4: Out-of-Scope / Negative Constraint Queries (41-50) ────────
    (
        "How do I deploy DevPilot on Kubernetes using Helm charts with horizontal pod autoscaling?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "What is the configuration for streaming Kafka events into Elasticsearch in DevPilot?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "How do I connect DevPilot to AWS Bedrock Claude 3.5 Sonnet using IAM roles?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "How do I configure GraphQL mutations with Apollo Federation in DevPilot?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "How is Redis Sentinel master-replica failover configured for distributed caching?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "How do I set up Stripe webhook subscriptions and billing checkout sessions in DevPilot?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "What is the procedure for training a custom LoRA adapter on Llama 3 using PyTorch FSDP?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "How do I compile DevPilot mobile clients for iOS using React Native and Xcode?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "How do I configure MongoDB replica sets with WiredTiger compression in DevPilot?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
    (
        "What is the gRPC protobuf service definition for real-time video streaming in DevPilot?",
        [],
        "I do not have enough information in the provided documents to answer this question.",
    ),
]


async def main():
    embedding_service = get_embedding_service()
    print(f"Building benchmarks/gold_standard_50.jsonl with {len(RAW_QUERIES)} queries...")

    # Pre-generate embeddings for all unique chunks
    unique_chunk_keys = list(CHUNKS_POOL.keys())
    unique_contents = [CHUNKS_POOL[k]["content"] for k in unique_chunk_keys]
    print(f"Generating embeddings for {len(unique_contents)} unique technical chunks...")
    embeddings = await embedding_service.generate_embeddings(unique_contents)
    for k, emb in zip(unique_chunk_keys, embeddings):
        CHUNKS_POOL[k]["embedding"] = emb

    # Distractor embeddings
    distractor_contents = [d["content"] for d in DISTRACTORS]
    d_embs = await embedding_service.generate_embeddings(distractor_contents)
    for d, emb in zip(DISTRACTORS, d_embs):
        d["embedding"] = emb

    all_records = []
    all_keys = list(CHUNKS_POOL.keys())

    for idx, (query, gt_keys, ref_ans) in enumerate(RAW_QUERIES, start=1):
        # Build corpus pool for this query: target chunk(s) + 4-6 diverse distractor chunks
        corpus_chunks = []
        # Add ground truth chunks
        for k in gt_keys:
            if k in CHUNKS_POOL:
                corpus_chunks.append(dict(CHUNKS_POOL[k]))

        # Add rotating distractors from other technical chunks
        distractor_candidates = [
            CHUNKS_POOL[k] for k in all_keys if k not in gt_keys
        ]
        # Pick 4 deterministic distractors based on idx
        for d_i in range(4):
            chosen = distractor_candidates[(idx * 3 + d_i) % len(distractor_candidates)]
            if chosen["chunk_id"] not in [c["chunk_id"] for c in corpus_chunks]:
                corpus_chunks.append(dict(chosen))

        # Add 1 general distractor
        gen_d = DISTRACTORS[idx % len(DISTRACTORS)]
        if gen_d["chunk_id"] not in [c["chunk_id"] for c in corpus_chunks]:
            corpus_chunks.append(dict(gen_d))

        record = {
            "query_id": f"q{idx:02d}",
            "query": query,
            "ground_truth_chunk_ids": gt_keys,
            "reference_answer": ref_ans,
            "corpus": corpus_chunks,
        }
        all_records.append(record)

    out_path = PROJECT_ROOT / "benchmarks" / "gold_standard_50.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")

    print(f"Successfully wrote {len(all_records)} queries to: {out_path}")
    print(f"File size: {out_path.stat().st_size} bytes")


if __name__ == "__main__":
    asyncio.run(main())
