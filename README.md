# DevPilot

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%20(async)-red?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED?logo=docker&logoColor=white)](https://www.docker.com)
[![CI Pipeline](https://img.shields.io/badge/CI-GitHub%20Actions-brightgreen?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Tested with Pytest](https://img.shields.io/badge/Pytest-61%2F61%20passing-brightgreen?logo=pytest&logoColor=white)](https://pytest.org)

---

## Milestone Status — Weeks 1–8 Complete

DevPilot is a production-grade, multi-tenant AI document intelligence platform built with modern async Python standards. At the **Week 8 milestone**, the platform features our production-winning **Approach A+B Hybrid (RRF-Blended Multilingual Cross-Encoder)** alongside bounded agentic workflows, multilingual evaluation sweeps, hybrid retrieval, and grounded answer synthesis:

| Capability | Status | Notes |
|:---|:---:|:---|
| **Async FastAPI & SQLAlchemy 2.0** | ✅ | Asynchronous connection pooling and declarative ORM |
| **Authentication & Tenant Isolation** | ✅ | `X-API-Key` header authentication; 401 unauthenticated & 403 cross-tenant isolation |
| **Document Ingestion Pipeline** | ✅ | SHA-256 deduplication, PyPDF/markdown extractors, sliding-window chunking (512/64) |
| **Background Processing Queue** | ✅ | FastAPI `BackgroundTasks` with independent `async_session_factory` sessions |
| **Dense Semantic Search** | ✅ | 384-dimensional FastEmbed (`BAAI/bge-small-en-v1.5`) & Multilingual (`paraphrase-multilingual-MiniLM-L12-v2`) |
| **Sparse BM25 & Multilingual Tokenizer** | ✅ | `rank-bm25` BM25Okapi with Unicode regex (`[\w\u0980-\u09ff\u200c\u200d]+`) and LRU caching |
| **Reciprocal Rank Fusion (RRF)** | ✅ | Formula-based candidate blending with constant $k=60$ |
| **Production Champion Reranker (Approach A+B)** | ✅ | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` + 20% RRF score blending (**0.8748 Global MRR, 80.0% Rank #1**) |
| **Script-Aware Edge Reranker (Approach A)** | ✅ | Regex script detection (`[\u0980-\u09ff]`) with dynamic bypass to RRF (148ms P50, 86.7MB RAM) |
| **Grounded RAG with Provenance** | ✅ | Synthesizes grounded answers with inline citations `[1]` and start/end character offsets |
| **Bounded Agentic Workflows** | ✅ | 4-phase FSM (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`), GuardedToolDispatcher, Pydantic v2 validation, per-tool timeout isolation, max 5 loop cap, structured `WorkflowReport` |
| **100-Query Multilingual Benchmark** | ✅ | Automated CLI benchmark evaluating English, Bengali script, and Romanized Banglish (`benchmarks/multilingual_gold_100.jsonl`) |
| **50-Query Parameter Sweep Benchmark** | ✅ | Automated CLI benchmark measuring Hit@k, MRR, P50/P95 latencies, and unsupported claims |
| **Docker & Docker Compose** | ✅ | Multi-stage build on `python:3.11-slim`, non-root user `devpilot`, persisted storage |
| **Continuous Integration (CI)** | ✅ | GitHub Actions workflow executing linting, `pytest`, and benchmark verification |

---

## Architecture

```
                       ┌────────────────────────────────────────────────────────┐
  Client Request       │              DevPilot FastAPI Application              │
  (X-API-Key Header)   │                                                        │
  ──────────────────►  │   Security Guard       FastAPI Router       Uvicorn    │
                       │   (401/403 Tenant)   (Async Endpoints)   (ASGI Server) │
                       └───────────────────────────┬────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┴──────────────────────────────┐
                    │                      Service Layer                          │
                    │                                                             │
                    │  LocalStorageService      EmbeddingService (Multilingual)   │
                    │  (SHA-256, 10MB limit)    BM25Okapi Unicode Retriever       │
                    │                           Reciprocal Rank Fusion (RRF k=60) │
                    │  chunk_text(512, 64)      Cross-Encoder Reranker (mmarco)   │
                    │  (Sliding Window)         Neural-Symbolic Consensus (20%)   │
                    │                           LLMService (Grounded + Citations) │
                    │                                                             │
                    │  GuardedToolDispatcher    BoundedAgent (4-Phase FSM)        │
                    │  (Pydantic Validation,    (SEARCH -> INSPECT ->             │
                    │   Timeouts, Isolation)     SUMMARIZE -> PROPOSE)            │
                    └──────────────────────────────┬──────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┴──────────────────────────────┐
                    │          SQLAlchemy 2.0 Async ORM & Data Layer              │
                    │                                                             │
                    │   Project (tenant_id)     DocumentChunk (384-dim vector)    │
                    │   Document (file metadata) ProcessingJob (PENDING/COMPLETED)│
                    │                                                             │
                    │         PostgreSQL 16 (Prod/Docker) / SQLite (Test)         │
                    └─────────────────────────────────────────────────────────────┘
```

### Retrieval, Ingestion & Agent Workflows

1. **Ingestion Flow:**
   ```
   POST /documents/upload ──► Validate X-API-Key & Tenant ──► Save File (SHA-256) ──► Enqueue Job
                                                                                          │
                                                        FastAPI BackgroundTask ◄──────────┘
                                                                │
                                            Extract Text (PDF/MD/TXT/PY)
                                                                │
                                            Sliding Window Chunker (512c, 64c overlap)
                                                                │
                                            Generate 384-d FastEmbed Vectors
                                                                │
                                            Persist DocumentChunk rows ──► Job COMPLETED
   ```

2. **Hybrid RAG Flow:**
   ```
   POST /projects/{id}/rag ──► Validate Tenant Access
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
        Dense Vector Similarity                 Sparse BM25 Keyword Search
        (Multilingual MiniLM / FastEmbed)       (Unicode BM25Okapi, in-memory cache)
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     ▼
                      Reciprocal Rank Fusion (RRF, k=60)
                                     ▼
                      Multilingual Cross-Encoder (mmarco-mMiniLMv2-L12)
                                     ▼
                      Neural-Symbolic Consensus (80% CE + 20% Normalized RRF)
                                     ▼
                      Grounded LLM Answer Synthesis + Citations [1]
   ```

3. **Bounded Agent Workflow:**
   ```
   POST /projects/{id}/agent/workflow ──► Validate Tenant Access
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        ▼                                               ▼
               GuardedToolDispatcher                             BoundedAgent FSM
          (Pydantic validation, timeouts,                (SEARCH ➔ INSPECT ➔ SUMMARIZE ➔ PROPOSE)
           phase boundary firewall)                                     │
                        │                                               ▼
                        └───────────────────────────────────────► WorkflowReport
                                                           (Audit logs + AgentProposal)
   ```

---

## Benchmark Results

### 1. Week 8 Multilingual 100-Query Benchmark (Head-to-Head Architectural Sweep)

Empirical results from our 100-query multilingual gold standard benchmark ([`benchmarks/multilingual_gold_100.jsonl`](benchmarks/multilingual_gold_100.jsonl)) evaluating 34 English technical queries, 33 native Bengali script queries, and 33 Romanized Banglish queries:

| Architecture Configuration | Recall@5 | Global MRR | Rank #1 Hits | English MRR | Bangla MRR | Banglish MRR | P50 (ms) | P95 (ms) | RAM Footprint |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Baseline (Un-guarded Monolingual)** | 0.8300 | 0.7015 | 63.0% | **0.8897** | 0.2788 ❌ | 0.9303 | 182.21 | 244.64 | **86.65 MB** |
| **2. Approach A (Script-Aware Bypass)** | 0.9500 | 0.7630 | 64.0% | **0.8897** | 0.4652 | 0.9303 | **148.65** ⚡ | **191.12** ⚡ | **86.65 MB** |
| **3. Approach B (Multilingual CE `mmarco-L12`)** | **0.9900** | 0.8675 | 79.0% | 0.7922 | **0.9051** 🚀 | 0.9076 | 221.35 | 419.55 | 448.77 MB |
| **4. Approach A+B Hybrid (Production Champion)** | 0.9800 | **0.8748** 🏆 | **80.0%** 🏆 | 0.8284 | 0.8581 | **0.9394** 🚀 | 232.12 | 419.04 | 448.77 MB |

> **Production Winner:** **Approach A+B Hybrid** achieves our highest precision across all slices by fusing deep cross-attention with 20% normalized lexical RRF consensus. See [`BENCHMARK.md`](BENCHMARK.md) and [`reports/WEEK_8_OPTIMIZATION_RESULT.md`](reports/WEEK_8_OPTIMIZATION_RESULT.md) for full architectural analysis and trade-off formulas.

### 2. Week 5 English Technical 50-Query Parameter Sweep

Empirical results from the 50-query parameter sweep ([`benchmarks/gold_standard_50.jsonl`](benchmarks/gold_standard_50.jsonl)) persisted to [`artifacts/benchmark_results.json`](artifacts/benchmark_results.json):

| Retrieval Mode | Chunk Size | Top-K | Hit@k | MRR | P50 Ret (ms) | P95 Ret (ms) | P50 Gen (ms) | P95 Gen (ms) | Unsupported Claims |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`vector_only`** | 512 | 3 | **1.00** | 0.97 | **6.83** | **10.04** | 0.04 | 0.05 | 23.67% |
| **`hybrid`** | 512 | 3 | **1.00** | 0.95 | **7.20** | **9.57** | 0.04 | 0.05 | 24.00% |
| **`hybrid_rerank`** | 512 | 3 | **1.00** | **1.00** | 125.68 | 184.29 | 0.05 | 0.06 | 26.00% |
| **`vector_only`** | 512 | 5 | **1.00** | 0.97 | **7.19** | **9.72** | 0.05 | 0.06 | 28.17% |
| **`hybrid`** | 512 | 5 | **1.00** | 0.95 | **7.28** | **10.40** | 0.04 | 0.06 | 28.33% |
| **`hybrid_rerank`** | 512 | 5 | **1.00** | **1.00** | 143.50 | 173.35 | 0.05 | 0.07 | 29.50% |

> See [`BENCHMARK.md`](BENCHMARK.md) for the full report, mathematical metric definitions, and architectural trade-off analysis.

---

## Quickstart with Docker Compose

The fastest way to run DevPilot locally with PostgreSQL and persistent storage volumes:

### 1. Launch Services
```bash
docker compose up -d --build
```

### 2. Verify Health
```bash
curl http://localhost:8000/api/v1/health
```

Output:
```json
{"status": "healthy", "service": "DevPilot", "version": "0.1.0", "database": "connected"}
```

- **Interactive Swagger Docs:** http://localhost:8000/docs
- **ReDoc API Spec:** http://localhost:8000/redoc

### 3. Stop Containers
```bash
docker compose down
```

---

## Local Development Setup

### 1. Prerequisites
- **Python 3.11+**
- Git

### 2. Virtual Environment & Dependencies
```bash
python -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# .\.venv\Scripts\Activate.ps1  # On Windows PowerShell

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 3. Environment Configuration
```bash
cp .env.example .env
```

### 4. Database Migrations
```bash
alembic upgrade head
```

### 5. Run the Application
```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

### 6. Run Test Suite & Benchmark Runner
```bash
# Run all 61 automated tests
pytest -v

# Run the 100-query multilingual benchmark sweep
python -m src.evaluation.runner --dataset benchmarks/multilingual_gold_100.jsonl --sweep --mock-llm

# Run head-to-head reranker comparison across all 4 architectures
python scripts/benchmark_head_to_head.py
```

---

## API Endpoints

All protected endpoints require an authenticated `X-API-Key` header:

| Method | Endpoint | Auth Required | Description |
|:------:|:---------|:---:|:------------|
| `GET` | `/api/v1/health` | No | Service status and async database connectivity ping |
| `POST` | `/api/v1/projects` | Yes | Create a new project (auto-assigned to tenant) |
| `GET` | `/api/v1/projects` | Yes | List tenant projects (paginated) |
| `GET` | `/api/v1/projects/{id}` | Yes | Get project by UUID (enforces tenant check) |
| `PATCH` | `/api/v1/projects/{id}` | Yes | Update project metadata (enforces tenant check) |
| `DELETE` | `/api/v1/projects/{id}` | Yes | Delete project and cascade documents/chunks |
| `POST` | `/api/v1/documents/upload` | Yes | Multipart upload → auto-ingest background job |
| `GET` | `/api/v1/documents` | Yes | List documents (filtered by project or tenant) |
| `GET` | `/api/v1/documents/{id}` | Yes | Get document metadata by UUID |
| `PATCH` | `/api/v1/documents/{id}` | Yes | Update document metadata |
| `DELETE` | `/api/v1/documents/{id}` | Yes | Delete document record |
| `GET` | `/api/v1/jobs/{id}` | Yes | Poll processing job status (`PENDING` / `COMPLETED`) |
| `GET` | `/api/v1/jobs` | Yes | List processing jobs (filter by status) |
| `POST` | `/api/v1/projects/{id}/search` | Yes | Multi-mode semantic search (`vector_only`, `hybrid`, `hybrid_rerank`) |
| `POST` | `/api/v1/projects/{id}/rag` | Yes | Grounded RAG answer synthesis with citation provenance |
| `POST` | `/api/v1/projects/{id}/agent/workflow` | Yes | Bounded 4-phase agentic research workflow (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`) |

---

## Project Structure

```text
e:\Devpilot\
├── .github/workflows/ci.yml          # GitHub Actions CI workflow (lint, test, benchmark)
├── .dockerignore                     # Docker build exclusions
├── Dockerfile                        # Multi-stage production container definition
├── docker-compose.yml                # Compose orchestration with PostgreSQL 16
├── BENCHMARK.md                      # 100-query multilingual & 50-query sweep report
├── STATUS.md                         # Milestones tracker (Weeks 1–8 complete)
├── LOG_DESCRIPTION.md                # 12-week engineering journal
├── pyproject.toml                    # Project metadata & tool config
├── requirements.txt                  # Production dependencies
├── requirements-dev.txt              # Testing and development dependencies
├── alembic/                          # Async database migrations
├── benchmarks/
│   ├── multilingual_gold_100.jsonl   # 100-query multilingual gold-standard benchmark
│   ├── gold_standard_50.jsonl        # 50-query evaluation benchmark dataset
│   └── eval_data.jsonl               # Baseline 5-query dataset
├── artifacts/
│   ├── head_to_head_comparison.json  # 4-way head-to-head reranker benchmark telemetry
│   ├── multilingual_benchmark_results.json # 100-query sweep results per language slice
│   └── benchmark_results.json        # 50-query baseline benchmark evaluation results
├── reports/
│   ├── WEEK_8_OPTIMIZATION_RESULT.md # Head-to-head reranker comparison & trade-off analysis
│   ├── WEEK_8_ERROR_ANALYSIS.md      # Multilingual retrieval failure pattern diagnosis
│   └── WEEK_7_ANALYSIS_REPORT.md     # Week 7 multilingual retrieval & agent analysis
├── scripts/
│   ├── benchmark_head_to_head.py     # 4-way architectural comparison benchmark runner
│   └── analyze_retrieval_errors.py   # Retrieval error classification & analysis script
├── src/
│   ├── main.py                       # FastAPI application factory & lifespan
│   ├── core/
│   │   ├── config.py                 # Centralized settings (chunking, reranker model, blending)
│   │   ├── database.py               # AsyncEngine & async_session_factory
│   │   ├── security.py               # X-API-Key auth & tenant isolation verification
│   │   └── exceptions.py             # Custom domain exceptions
│   ├── models/                       # SQLAlchemy 2.0 ORM models
│   │   ├── project.py                # Project with tenant_id and owner_api_key
│   │   ├── document.py               # Document metadata
│   │   ├── document_chunk.py         # 384-dim vector chunk storage
│   │   └── processing_job.py         # ProcessingJob & JobStatus enum
│   ├── schemas/                      # Pydantic v2 validation schemas
│   ├── services/
│   │   ├── storage.py                # LocalStorageService (SHA-256, 10MB limit)
│   │   ├── extractor.py              # PDF/MD/TXT/PY file text extraction
│   │   ├── chunker.py                # Sliding-window chunker (512/64)
│   │   ├── embedding.py              # Multilingual & FastEmbed BGE-384 async service
│   │   ├── retrieval/                # Advanced retrieval subsystem
│   │   │   ├── hybrid.py             # Unicode BM25Okapi, RRF (k=60), in-memory cache
│   │   │   ├── pipeline.py           # Unified multi-mode search pipeline
│   │   │   └── reranker.py           # Multilingual cross-encoder & RRF score blending
│   │   ├── agent/                    # Bounded agentic workflow subsystem
│   │   │   ├── schemas.py            # FSM phases, tool schemas, AgentProposal, WorkflowReport
│   │   │   ├── tools.py              # Real data-bound tools (search, inspect, summarize)
│   │   │   └── workflow.py           # GuardedToolDispatcher & BoundedAgent FSM
│   │   └── llm.py                    # Grounded answer synthesis & citations
│   ├── evaluation/
│   │   ├── runner.py                 # Multilingual benchmark runner & parameter sweep CLI
│   │   ├── metrics.py                # Hit@k, MRR, latency, unsupported claims rate
│   │   └── benchmark.py              # Legacy evaluation runner helpers
│   └── api/v1/endpoints/             # REST endpoints (auth, projects, docs, search, rag, agent)
└── tests/                            # 61 integration tests (100% green)
```

---

## License

[MIT License](LICENSE)
