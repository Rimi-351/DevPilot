# DevPilot

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%20(async)-red?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED?logo=docker&logoColor=white)](https://www.docker.com)
[![CI Pipeline](https://img.shields.io/badge/CI-GitHub%20Actions-brightgreen?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Tested with Pytest](https://img.shields.io/badge/Pytest-54%2F54%20passing-brightgreen?logo=pytest&logoColor=white)](https://pytest.org)

---

## Milestone Status — Weeks 1–6 Complete

DevPilot is a production-grade, multi-tenant AI document intelligence platform built with modern async Python standards. At the **Week 6 milestone**, the platform features a complete bounded agentic workflow alongside its hybrid retrieval and grounded answer synthesis pipeline:

| Capability | Status | Notes |
|:---|:---:|:---|
| **Async FastAPI & SQLAlchemy 2.0** | ✅ | Asynchronous connection pooling and declarative ORM |
| **Authentication & Tenant Isolation** | ✅ | `X-API-Key` header authentication; 401 unauthenticated & 403 cross-tenant isolation |
| **Document Ingestion Pipeline** | ✅ | SHA-256 deduplication, PyPDF/markdown extractors, sliding-window chunking (512/64) |
| **Background Processing Queue** | ✅ | FastAPI `BackgroundTasks` with independent `async_session_factory` sessions |
| **Dense Semantic Search** | ✅ | 384-dimensional FastEmbed (`BAAI/bge-small-en-v1.5`) on ONNX Runtime |
| **Sparse BM25 Search & In-Memory Cache** | ✅ | `rank-bm25` BM25Okapi with hash-invalidated LRU caching |
| **Reciprocal Rank Fusion (RRF)** | ✅ | Formula-based candidate blending with constant $k=60$ |
| **Cross-Encoder Reranker** | ✅ | `cross-encoder/ms-marco-MiniLM-L-6-v2` delivering **1.00 MRR** with fallback |
| **Grounded RAG with Provenance** | ✅ | Synthesizes grounded answers with inline citations `[1]` and start/end character offsets |
| **Bounded Agentic Workflows** | ✅ | 4-phase FSM (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`), GuardedToolDispatcher, Pydantic v2 validation, per-tool timeout isolation, max 5 loop cap, structured `WorkflowReport` |
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
                    │  LocalStorageService      EmbeddingService (FastEmbed 384) │
                    │  (SHA-256, 10MB limit)    BM25Okapi Sparse Retriever        │
                    │                           Reciprocal Rank Fusion (RRF k=60) │
                    │  chunk_text(512, 64)      Cross-Encoder Reranker (MiniLM)   │
                    │  (Sliding Window)         LLMService (Grounded + Citations) │
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
        (Cosine distance, FastEmbed)            (rank-bm25, in-memory cache)
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     ▼
                      Reciprocal Rank Fusion (RRF, k=60)
                                     ▼
                      Cross-Encoder Reranker (ms-marco-MiniLM)
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

## Benchmark Results (50-Query Gold Standard)

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
# Run all 54 automated tests
pytest -v

# Run the 50-query retrieval benchmark parameter sweep
python -m src.evaluation.runner --dataset benchmarks/gold_standard_50.jsonl --sweep --mock-llm
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
├── BENCHMARK.md                      # 50-query benchmark & parameter sweep report
├── STATUS.md                         # Milestones tracker (Weeks 1–5 complete)
├── LOG_DESCRIPTION.md                # 12-week engineering journal
├── pyproject.toml                    # Project metadata & tool config
├── requirements.txt                  # Production dependencies
├── requirements-dev.txt              # Testing and development dependencies
├── alembic/                          # Async database migrations
├── benchmarks/
│   ├── gold_standard_50.jsonl        # 50-query evaluation benchmark dataset
│   └── eval_data.jsonl               # Baseline 5-query dataset
├── artifacts/
│   └── benchmark_results.json        # Latest persisted benchmark evaluation results
├── src/
│   ├── main.py                       # FastAPI application factory & lifespan
│   ├── core/
│   │   ├── config.py                 # Centralized settings (chunk size 512, overlap 64)
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
│   │   ├── embedding.py              # FastEmbed BGE-384 async service
│   │   ├── retrieval/                # Advanced retrieval subsystem
│   │   │   ├── hybrid.py             # BM25Okapi, RRF (k=60), in-memory cache
│   │   │   ├── pipeline.py           # Unified multi-mode search pipeline
│   │   │   └── reranker.py           # Cross-encoder reranker with fallback
│   │   └── llm.py                    # Grounded answer synthesis & citations
│   ├── evaluation/
│   │   ├── runner.py                 # Benchmark runner & parameter sweep CLI
│   │   └── metrics.py                # Hit@k, MRR, latency, unsupported claims rate
│   └── api/v1/endpoints/             # REST endpoints (auth, projects, docs, search, rag)
└── tests/                            # 48 integration tests (100% green)
```

---

## License

[MIT License](LICENSE)
