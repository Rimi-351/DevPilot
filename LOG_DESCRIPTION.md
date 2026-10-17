# 🚀 DevPilot: 12-Week Engineering Journey & System Log

> **Repository:** `Rimi-351/DevPilot`  
> **Stack:** FastAPI, SQLAlchemy 2.0 (Async), SQLite / PostgreSQL, Alembic, Pydantic v2, Pytest

---

## 🗺️ 12-Week Master Roadmap

| Level | Week | Milestone Topic | Deliverable |
| :--- | :---: | :--- | :--- |
| **L1** | **W01** | **Backend Foundation** | FastAPI async scaffold, schemas, DB migrations, error handlers. |
| **L1** | **W02** | **Document Ingestion** | Upload API, SHA-256 storage, sliding chunker, background jobs. |
| **L2** | **W03** | **Retrieval Pipeline** | Embeddings, vector search, chunk provenance, and metadata references. |
| **L2** | **W04** | **RAG & Evaluation** | Grounded answers, citations, benchmark dataset, failure analysis. |
| **L2** | **W05** | **Search Quality** | Hybrid search, cross-encoder reranking, and automated evaluation. |
| **L3** | **W06** | **Agentic Workflows** | Model tool calling, structured outputs, validation, timeouts. |
| **L3** | **W07** | **MCP Integration** | Model Context Protocol server exposing docs & metadata tools. |
| **L3** | **W08** | **Security & Guardrails** | Human approvals, untrusted input isolation, prompt injection tests. |
| **L4** | **W09** | **Docker & CI/CD** | Containerization, Compose multi-env, GitHub Actions pipelines. |
| **L4** | **W10** | **Observability** | OpenTelemetry tracing, latency tracking, failure timelines. |
| **L4** | **W11** | **System Verification** | End-to-end stress tests, benchmark reports, architecture docs. |
| **L4** | **W12** | **Portfolio & Defense** | Code polishing, interview prep, and live architecture walkthrough. |

---

## 📦 Completed Milestones

---

### 🔹 Week 1: Core Backend & Data Architecture


```

Client (HTTP) ──► Pydantic v2 (Input Validation) ──► FastAPI Router ──► Async SQLAlchemy 2.0 ──► SQLite / PostgreSQL

```

#### 1. What Was Built
* **Layered Clean Architecture:** Partitioned into `core/`, `models/`, `schemas/`, and `api/v1/`.
* **Entities:** Relational tables for `Project`, `Document`, and `ProcessingJob`.
* **Database Drivers:** Asynchronous connections supporting local `aiosqlite` and production `asyncpg`.
* **Migrations:** Automated schema versioning via Alembic.
* **Error Boundaries:** Centralized RFC-7807 error formatters.

#### 2. Why & What Problems It Resolves
* **Zero Database Freezes:** Async I/O frees worker threads to handle other clients while waiting on the database.
* **Early Failure:** Pydantic v2 rejects malformed JSON payloads before database queries run.
* **Portability:** Switching between SQLite and PostgreSQL requires altering only one `.env` parameter.

#### 3. Architecture Trade-offs
* **SQLAlchemy 2.0 vs. Raw SQL:** Adds learning overhead, but eliminates SQL injection and decouples database vendor lock-in.
* **FastAPI vs. Django:** Lacks out-of-the-box admin dashboards, but runs significantly faster and generates automated OpenAPI documentation at `/docs`.

#### 💡 Interview Cheat Sheet
> *"In Week 1, I built the modular backend foundation of DevPilot using FastAPI and SQLAlchemy 2.0 with asynchronous I/O. I modeled Projects, Documents, and Jobs with Alembic migrations, designed flexible database switching between SQLite and PostgreSQL, and implemented validation using Pydantic v2."*

---

### 🔹 Week 2: Ingestion, Deduplication & Chunking


```

File Upload ──► SHA-256 Hash ──► Streaming Storage ──► DB Record (PENDING)
│
(Background Worker)
▼
Text Extraction (PDF/TXT)
▼
Sliding-Window Chunker
▼
Job (COMPLETED)

```

#### 1. What Was Built
* **Binary Upload:** `POST /api/v1/documents/upload` accepting multipart files.
* **Streaming Storage:** `LocalStorageService` with memory-safe `aiofiles` writing to `storage/uploads/`.
* **Deduplication:** SHA-256 content hashing to ensure identical files share storage.
* **Text Parser:** Plain text, source code, and multi-page PDF extraction using `pypdf`.
* **Sliding-Window Chunker:** Slices text into 500-character segments with 50-character overlaps and offset tracking.
* **Task Lifecycle:** FastAPI background workers managing job state transitions (`PENDING` -> `IN_PROGRESS` -> `COMPLETED`).
* **Test Harness:** 22 passing tests covering edge cases, boundary offsets, and HTTP errors.

#### 2. Why & What Problems It Resolves
* **Fast User Feedback:** Uploads return an HTTP 201/202 instantly; CPU-heavy parsing runs in the background.
* **RAM Protection:** Streaming buffers avoid loading 10MB+ files into system memory all at once.
* **Context Preservation:** Sliding-window overlap avoids splitting sentences or ideas in half across chunk borders.

#### 3. Architecture Trade-offs
* **FastAPI BackgroundTasks vs. Celery:** Zero external services (no Redis/RabbitMQ required), but jobs live in memory and will terminate if the web process restarts.
* **Sliding Chunker vs. Semantic/AST Chunker:** Language-agnostic and fast (O(n) character iterations), but splits based on length rather than grammatical syntax.

#### 💡 Interview Cheat Sheet
> *"In Week 2, I implemented an asynchronous document ingestion pipeline. Uploaded files are hashed with SHA-256 for deduplication and saved via non-blocking streams. An asynchronous background task extracts text from PDFs and source code, processes it through a sliding-window chunker with character offsets, and updates the job lifecycle state in SQLite."*

---

### 🔹 Week 3: Retrieval Pipeline, Chunk Persistence & Semantic Search


```

Query (HTTP) ──► Query Embedding (fastembed/BGE) ──► Cosine Similarity Match ──► Ranked Chunks with Provenance
                                                          ▲
                                                          │
Stored Chunks & Embeddings (SQLite / PostgreSQL JSON) ────┘

```

#### 1. What Was Built
* **Vector Embedding Service:** Asynchronous `EmbeddingService` in `src/services/embedding.py` using `fastembed` (BAAI/bge-small-en-v1.5, 384 dimensions) with deterministic mock fallback for instant test runs.
* **Chunk Entity & Dialect Portability:** `DocumentChunk` model with JSON-serialized float vectors for dialect-independent vector storage across SQLite & PostgreSQL.
* **Database Migrations:** Alembic revision and upgrade adding `document_chunks` table with cascade foreign keys and indexes.
* **Pipeline Persistence:** Enriched `process_document_background` worker to automatically embed extracted text chunks and bulk-insert `DocumentChunk` records.
* **Semantic Search Endpoint:** `POST /api/v1/projects/{project_id}/search` computing cosine similarity, sorting top-k results, and guaranteeing multi-tenant project isolation.
* **End-to-End Provenance:** Search results retain full provenance metadata (`filename`, `chunk_index`, `start_offset`, `end_offset`, `score`).
* **Test Suite Expansion:** 5 new integration tests verifying chunk persistence, relevance ranking, multi-tenant isolation, provenance integrity, and 404 boundaries (27 total passing tests).

#### 2. Why & What Problems It Resolves
* **Semantic Discovery:** Users can search concepts and intent rather than exact keyword substrings.
* **Document Provenance:** Citations accurately locate the exact text span in source files using byte/character offsets.
* **Database Portability:** Using JSON vector storage avoids hard vendor locks while remaining compatible with SQLite for local development and PostgreSQL for production.

#### 3. Architecture Trade-offs
* **In-Memory Cosine Similarity vs. pgvector / Dedicated Vector DB:** Simplifies initial architecture and local zero-dependency testing without requiring C extensions or external vector databases, while providing an upgrade path to pgvector or Qdrant for massive corpora.
* **CPU ONNX Runtime (fastembed) vs. PyTorch (sentence-transformers):** Significantly lighter dependency footprint (15MB vs. 800MB+ for PyTorch) and faster CPU inference.

#### 💡 Interview Cheat Sheet
> *"In Week 3, I engineered the document retrieval and semantic search pipeline for DevPilot. I modeled persistent DocumentChunks with JSON vector representations and Alembic migrations. In the background ingestion pipeline, text chunks are asynchronously vectorized using fastembed (bge-small-en-v1.5) and persisted with character offsets. I then implemented a multi-tenant semantic search endpoint computing cosine similarity over query and chunk embeddings, returning top-k ranked chunks with full file and offset provenance."*
