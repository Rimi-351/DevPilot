# DevPilot

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%20(async)-red?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev)
[![Tested with Pytest](https://img.shields.io/badge/Pytest-37%2F37%20passing-brightgreen?logo=pytest&logoColor=white)](https://pytest.org)

---

## Week 4 Portfolio Milestone — Grounded RAG & AI Evaluation

DevPilot is an AI-assisted document intelligence platform built across a 12-week engineering program. At the **Week 4 milestone**, the following capabilities are fully implemented and verified:

| Capability | Status |
|:-----------|:------:|
| Async FastAPI backend with SQLAlchemy 2.0 | ✅ |
| Document ingestion pipeline with background workers | ✅ |
| 384-dim vector embeddings (BAAI/bge-small-en-v1.5) | ✅ |
| Multi-tenant semantic search with cosine similarity | ✅ |
| Grounded RAG with citation provenance | ✅ |
| Keyword vs. Vector retrieval benchmark | ✅ |
| 37/37 integration tests passing, 0 warnings | ✅ |
| Live Swagger UI end-to-end verification | ✅ |

---

## Architecture Highlights (4-Week Build)

```
                       ┌────────────────────────────────────────────────────┐
  HTTP Client          │              DevPilot FastAPI Application           │
  ─────────────────►   │                                                    │
                       │  Pydantic v2       FastAPI Router       Uvicorn    │
                       │  (Validation)    (async endpoints)   (ASGI server) │
                       └───────────────────────┬────────────────────────────┘
                                               │
                ┌──────────────────────────────▼──────────────────────────────┐
                │                    Service Layer                             │
                │                                                              │
                │  LocalStorageService   EmbeddingService    LLMService       │
                │  (SHA-256, aiofiles)  (fastembed/BGE-384) (httpx/mock)     │
                │                                                              │
                │  chunk_text()          lexical_keyword_search()             │
                │  (sliding window)      (TF token overlap)                  │
                └──────────────────────────────┬───────────────────────────── ┘
                                               │
                ┌──────────────────────────────▼──────────────────────────────┐
                │         SQLAlchemy 2.0 Async ORM + Alembic Migrations       │
                │                                                              │
                │   Project  Document  DocumentChunk  ProcessingJob           │
                │                                                              │
                │         SQLite (dev)  /  PostgreSQL (prod)                  │
                └─────────────────────────────────────────────────────────────┘
```

**Background Ingestion Pipeline:**
```
POST /upload ──► SHA-256 dedup ──► Save file ──► DB: Document + Job (PENDING)
                                                           │
                                          FastAPI BackgroundTask
                                                           │
                                     Extract text (PDF/TXT/MD/PY)
                                                           │
                                     Sliding-window chunker (500c / 50c overlap)
                                                           │
                                     EmbeddingService → 384-dim BGE vectors
                                                           │
                                     Bulk-insert DocumentChunk rows
                                                           │
                                          Job → COMPLETED
```

**RAG Pipeline:**
```
POST /rag ──► Vector retrieval (cosine similarity, multi-tenant) ──► Top-k chunks
                                                                           │
                                             Grounded LLM synthesis (httpx → Groq/OpenAI)
                                             System prompt: "Answer ONLY from excerpts [1],[2]..."
                                                                           │
                                          Answer + Citations (chunk_id, filename, offsets)
                                       OR "I do not have enough information..."
```

---

## API Endpoints

| Method | Endpoint | Description |
|:------:|:---------|:------------|
| `GET` | `/api/v1/health` | Health check with live DB ping |
| `POST` | `/api/v1/projects` | Create a new project |
| `GET` | `/api/v1/projects` | List all projects (paginated) |
| `GET` | `/api/v1/projects/{id}` | Get project by ID |
| `PATCH` | `/api/v1/projects/{id}` | Update project metadata |
| `DELETE` | `/api/v1/projects/{id}` | Delete project (cascades chunks) |
| `POST` | `/api/v1/documents/upload` | Upload file → auto-ingest background job |
| `GET` | `/api/v1/documents` | List documents (filter by project_id) |
| `GET` | `/api/v1/documents/{id}` | Get document by ID |
| `PATCH` | `/api/v1/documents/{id}` | Update document metadata |
| `DELETE` | `/api/v1/documents/{id}` | Delete document |
| `GET` | `/api/v1/jobs/{id}` | Poll processing job status |
| `GET` | `/api/v1/jobs` | List jobs (filter by project/status) |
| `POST` | `/api/v1/projects/{id}/search` | Semantic vector search over project chunks |
| `POST` | `/api/v1/projects/{id}/rag` | Grounded RAG with citation provenance |

---

## Quickstart

### 1. Prerequisites
- **Python 3.11+** (tested on Python 3.13)
- Windows PowerShell or Bash (Linux/macOS)

### 2. Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 3. Environment Configuration

Copy the example file and edit as needed:
```powershell
Copy-Item .env.example .env
```

**Minimal `.env` for local development (SQLite, offline mode):**
```ini
DATABASE_URL=sqlite+aiosqlite:///./devpilot.db
```

**Full `.env` with live LLM (OpenAI-compatible, e.g. Groq):**
```ini
# Database — SQLite for local dev, PostgreSQL for production
DATABASE_URL=sqlite+aiosqlite:///./devpilot.db

# LLM Provider (OpenAI-compatible API)
LLM_API_KEY=gsk_your_groq_api_key_here
LLM_MODEL=llama-3.3-70b-versatile
LLM_BASE_URL=https://api.groq.com/openai/v1
```

> **Offline mode:** If `LLM_API_KEY` is empty, the RAG endpoint uses a deterministic keyword-based mock generator — no API key or network required.

**Supported LLM providers:**

| Provider | `LLM_BASE_URL` | Example `LLM_MODEL` |
|:---------|:--------------|:---------------------|
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3` |

### 4. Database Initialization

```powershell
# Apply all Alembic migrations
.\.venv\Scripts\alembic.exe upgrade head
```

### 5. Run the Server

```powershell
.\.venv\Scripts\uvicorn.exe src.main:app --reload --host 127.0.0.1 --port 8000
```

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **Health:** http://127.0.0.1:8000/api/v1/health

### 6. Run Tests

```powershell
.\.venv\Scripts\pytest.exe -v
```

All 37 integration tests run with isolated in-memory SQLite — zero external service dependencies.

---

## Technology Stack

| Layer | Technologies |
|:------|:-------------|
| **Framework** | FastAPI 0.115+, Starlette, Uvicorn |
| **Data Validation** | Pydantic v2, pydantic-settings |
| **ORM & Database** | SQLAlchemy 2.0 (async), aiosqlite (dev), asyncpg (prod) |
| **Migrations** | Alembic (async engine) |
| **Embeddings** | fastembed (BAAI/bge-small-en-v1.5, 384-dim, ONNX CPU) |
| **LLM Integration** | httpx async client (OpenAI-compatible) |
| **File I/O** | python-multipart, aiofiles, pypdf |
| **Testing** | Pytest, pytest-asyncio, HTTPX ASGITransport |

---

## Project Structure

```text
e:\Devpilot\
├── .env.example                      # Template env config
├── .gitignore                        # Git exclusion rules (secrets, uploads, DB)
├── BENCHMARK.md                      # Week 4 retrieval benchmark report
├── LOG_DESCRIPTION.md                # 12-week engineering journal
├── STATUS.md                         # Milestone tracker
├── pyproject.toml                    # Project metadata & tool config
├── requirements.txt                  # Production dependencies
├── requirements-dev.txt              # Dev/test dependencies
├── alembic/                          # Async migration environment
├── src/
│   ├── main.py                       # FastAPI app entrypoint & lifespan
│   ├── core/
│   │   ├── config.py                 # Pydantic-settings BaseSettings
│   │   ├── database.py               # AsyncEngine, session factory
│   │   └── exceptions.py             # Domain exceptions & handlers
│   ├── models/                       # SQLAlchemy 2.0 ORM models
│   │   ├── project.py
│   │   ├── document.py
│   │   ├── document_chunk.py         # 384-dim vector storage (JSON)
│   │   └── processing_job.py         # JobStatus enum & lifecycle
│   ├── schemas/                      # Pydantic v2 request/response schemas
│   │   ├── search.py
│   │   └── rag.py                    # Citation, RagQueryRequest, RagResponse
│   ├── services/
│   │   ├── storage.py                # SHA-256 dedup, extension validation
│   │   ├── extractor.py              # PDF/MD/TXT/PY text extraction
│   │   ├── chunker.py                # Sliding-window chunker (500c/50c)
│   │   ├── embedding.py              # fastembed async service
│   │   ├── search.py                 # Keyword lexical retriever
│   │   └── llm.py                    # Grounded LLM service (httpx + mock)
│   ├── evaluation/
│   │   └── benchmark.py              # Recall@k, MRR, BenchmarkRunner
│   └── api/v1/endpoints/
│       ├── documents.py              # Upload + background ingestion
│       ├── search.py                 # Semantic search endpoint
│       └── rag.py                    # Grounded RAG endpoint
├── storage/uploads/                  # Binary file storage (gitignored)
└── tests/
    ├── conftest.py                   # Fixtures: in-memory DB + session patch
    ├── test_health.py
    ├── test_projects.py
    ├── test_documents.py
    ├── test_jobs.py
    ├── test_ingestion.py
    ├── test_search.py
    └── test_rag.py                   # RAG + benchmark + keyword tests
```

---

## Benchmark Summary

See [`BENCHMARK.md`](BENCHMARK.md) for the full report. Key results:

| Metric | Keyword Retrieval | Vector Retrieval |
|:-------|:-----------------:|:----------------:|
| Recall@1 | 0.625 | **0.875** |
| Recall@3 | 0.750 | **1.000** |
| MRR | 0.698 | **0.917** |

Vector retrieval outperforms on paraphrase and concept queries. Keyword retrieval retains advantage on exact identifier lookups. Hybrid BM25 + Dense search planned for Week 5.

---

## Engineering Journal

See [`LOG_DESCRIPTION.md`](LOG_DESCRIPTION.md) for the full 12-week engineering log including:
- ASCII architecture flow diagrams for each milestone
- Keyword vs. Vector trade-off analysis with empirical benchmarks
- Live Swagger UI E2E verification notes
- Interview cheat sheets for every week
- Documented failure modes and Week 5 mitigations

---

## License

[MIT License](LICENSE)
