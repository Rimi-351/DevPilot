# DevPilot Project Status

**Current Target:** Week 5 — Search Quality  
**Status:** Week 4 COMPLETE — Portfolio Milestone Achieved  
**Last Verified:** `.venv\Scripts\pytest.exe -v` → **37/37 integration tests passing, 0 warnings**  

---

## Completed Deliverables

### Week 4 — Grounded RAG, Citations & AI Evaluation (Completed)

1. **Dependencies & LLM Configuration**
   - Added `httpx>=0.28.0` to `requirements.txt` and `pyproject.toml`.
   - Updated `src/core/config.py` with optional LLM configurations:
     - `LLM_API_KEY`: str = ""
     - `LLM_MODEL`: str = "gpt-4o-mini"
     - `LLM_BASE_URL`: str = "https://api.openai.com/v1"

2. **Grounded LLM Service (`src/services/llm.py`)**
   - Implemented asynchronous `LLMService` class with `generate_grounded_answer(query: str, context_chunks: list[dict]) -> tuple[str, list[dict]]`.
   - Strict system prompt instructing model to answer solely using provided excerpts labeled `[1]`, `[2]`, place citation markers next to factual claims, and return canonical refusal `"I do not have enough information in the provided documents to answer this question."` when evidence is lacking.
   - Built deterministic offline mock generator utilizing keyword-based semantic simulation for zero-cost, hermetic testing.
   - Registered singleton factory `get_llm_service()` in `src/services/__init__.py`.

3. **RAG Schemas & Endpoint**
   - Defined Pydantic v2 schemas in `src/schemas/rag.py`:
     - `RagQueryRequest`: query (str, min_length=1), top_k (int = 3, ge=1, le=10), temperature (float = 0.0, ge=0.0, le=1.0).
     - `Citation`: citation_id (int), chunk_id (UUID), document_id (UUID), filename (str), start_offset (int), end_offset (int).
     - `RagResponse`: query (str), answer (str), citations (list[Citation]), chunks_evaluated (int).
   - Implemented `POST /api/v1/projects/{project_id}/rag` in `src/api/v1/endpoints/rag.py`:
     - Verifies project existence (returns HTTP 404 if not found).
     - Reuses vector cosine similarity retrieval to fetch top-k chunks.
     - Formats context excerpts with 1-based citation indices [1], [2], ...
     - Synthesizes grounded answers via `LLMService`.
     - Maps citation markers back to exact chunk provenance and character offsets.
   - Mounted RAG router under `/projects` in `src/api/v1/api.py`.

4. **Information Retrieval Benchmarking (`src/evaluation/benchmark.py`)**
   - Implemented IR metrics: `compute_recall_at_k`, `compute_reciprocal_rank`, and `compute_mrr` (Mean Reciprocal Rank).
   - Expanded `DEFAULT_BENCHMARK_DATASET` to **8 items**: 5 standard domain-specific query-evidence pairs + 3 explicit failure scenarios (`lexical_gap`, `boundary_split`, `unanswerable`) with `expected_answer` and `category` fields.
   - `BenchmarkRunner.compare_retrieval_modes()` computes Recall@1, Recall@3, MRR for both `keyword` and `vector` modes side-by-side.

5. **Keyword Lexical Retrieval Baseline (`src/services/search.py`)**
   - `lexical_keyword_search(query, chunks)` — TF token overlap scorer, O(n) over chunk corpus.
   - Benchmarked: Keyword Recall@1=0.625, MRR=0.698 vs. Vector Recall@1=0.875, MRR=0.917.
   - Confirms vector dominance on concept queries; keyword wins on exact identifier lookups.

6. **Background Task Session Fix (`tests/conftest.py` & `src/api/v1/endpoints/documents.py`)**
   - Root cause: `async_session_factory` in `process_document_background` was bound to production engine at import time; test engine was never seen by background tasks.
   - Fix: `conftest.py` now monkey-patches `src.core.database.async_session_factory` AND `src.api.v1.endpoints.documents.async_session_factory` with the test `session_factory`.
   - Upload endpoint now calls `await db.commit()` before `background_tasks.add_task(...)` to eliminate the race where the background task opened a fresh session before the job row was committed.
   - All `add_task` arguments converted to `str` primitives to ensure reliable BackgroundTasks serialization.

7. **Pytest Integration & Evaluation Coverage (`tests/test_rag.py`)**
   - `test_end_to_end_grounded_rag`: File upload → RAG synthesis → citation markers `[1]` and provenance offsets verified.
   - `test_ungrounded_negative_query`: Queries for missing topics return polite refusal without hallucination and empty citations.
   - `test_rag_multi_tenant_isolation`: Verifies Project A queries never synthesize or cite Project B chunks.
   - `test_benchmark_metrics_calculation`: Validates Recall@k, Reciprocal Rank, and MRR mathematical accuracy.
   - `test_benchmark_runner_with_retriever`: Verifies asynchronous benchmark execution against dataset.
   - `test_rag_nonexistent_project_returns_404`: Validates HTTP 404 boundary.
   - `test_rag_empty_project_returns_polite_rejection`: Validates empty project handling.
   - `test_rag_query_validation_error`: Validates HTTP 422 constraints on query length, top_k, and temperature.
   - `test_lexical_keyword_search`: Validates lexical token overlap ranking.
   - `test_compare_retrieval_modes`: Validates BenchmarkRunner side-by-side keyword vs. vector evaluation.
   - **Total test suite: 37 passing tests (up from 35), 0 warnings.**

8. **Live E2E Swagger UI Verification**
   - Uploaded `company_policy.txt` via Swagger UI → job `PENDING → IN_PROGRESS → COMPLETED` automatically.
   - RAG query returned grounded answer with inline `[1]` citation, `start_offset=0`, `end_offset=162`.
   - Multi-tenant isolation verified: Project A cannot retrieve or cite Project B chunks (canonical refusal returned).

9. **BENCHMARK.md Report Generated**
   - Side-by-side Keyword vs. Vector comparison table (Recall@1, Recall@3, MRR).
   - 3 documented failure cases with root causes and Week 5 mitigations.
   - Live E2E Swagger UI verification notes with exact offsets and citation proof.

---

### Week 3 — Document Retrieval Pipeline, Chunk Persistence & Semantic Search (Completed)

1. **Dependencies & Embedding Integration**
   - Added `fastembed>=0.5.0` and `numpy>=1.26.0` to `requirements.txt` and `pyproject.toml`.
   - Installed into isolated `.venv` environment.
   - Built asynchronous `EmbeddingService` (`src/services/embedding.py`):
     - `generate_embeddings(texts: list[str]) -> list[list[float]]` and `generate_query_embedding(text: str) -> list[float]`.
     - Supports `fastembed` with lightweight models (e.g. `BAAI/bge-small-en-v1.5`, 384 dimensions) and non-blocking `asyncio.to_thread` execution.
     - Deterministic normalized 384-dimensional fallback for fast test execution without network dependency.

2. **Document Chunk Persistence & Data Architecture**
   - Created `DocumentChunk` model (`src/models/document_chunk.py`):
     - Table: `document_chunks`
     - Columns: `id` (UUID), `document_id` (FK -> documents.id ondelete CASCADE), `project_id` (FK -> projects.id ondelete CASCADE), `chunk_index` (int), `content` (text), `start_offset` (int), `end_offset` (int), `embedding` (JSON dialect-portable float array), `created_at` (DateTime with tz).
   - Exported `DocumentChunk` in `src/models/__init__.py`.
   - Added `chunks` cascade relationship on `Document` model.
   - Generated and applied Alembic migration `39fae4a3336b_create_document_chunks_table.py` (`upgrade head`).

3. **Background Ingestion & Embedding Pipeline**
   - Updated `process_document_background` in `src/api/v1/endpoints/documents.py`:
     - Text extraction -> sliding-window chunking -> vector embedding generation via `EmbeddingService`.
     - Bulk-persisted `DocumentChunk` instances linked to document and project.
     - Updated `ProcessingJob` metadata: `{"chunks_count": ..., "embedded": True, "dimensions": 384}`.
     - Maintained graceful failure boundary and status transitions.

4. **Semantic Search & Provenance Endpoint**
   - Defined Pydantic v2 schemas (`src/schemas/search.py`): `SearchQueryRequest`, `SearchChunkResult`, and `SearchResponse`.
   - Implemented `POST /api/v1/projects/{project_id}/search` (`src/api/v1/endpoints/search.py`):
     - Validates project existence (returns HTTP 404 if not found).
     - Generates query vector embedding.
     - Fetches project chunks joined with `Document` for filename resolution.
     - Computes cosine similarity scores, sorts descending, and returns `top_k` results with complete provenance (`filename`, `start_offset`, `end_offset`, `chunk_index`).
   - Registered search router in `src/api/v1/api.py`.

5. **Pytest Integration Coverage (`tests/test_search.py`)**
   - End-to-end document upload -> background embedding -> DB row verification in `document_chunks`.
   - Semantic query relevance and cosine similarity ranking.
   - Strict multi-tenant isolation (Project A queries never return Project B chunks).
   - Provenance verification (accurate offsets, filename, document ID, chunk ID).
   - HTTP 404 validation for non-existent projects.

---

### Week 2 — Document Ingestion Pipeline (Completed)

1. **Ingestion & Storage Dependencies**
   - Added `python-multipart`, `pypdf`, and `aiofiles` to `requirements.txt` and `pyproject.toml`.
   - Installed into isolated `.venv` environment.

2. **Local Storage Service (`src/services/storage.py`)**
   - Implemented asynchronous `LocalStorageService`.
   - File extension validation (`.pdf`, `.md`, `.txt`, `.py`) and size constraint checks (max 10MB configurable via `Settings`).
   - Content hashing via hexadecimal SHA-256 to ensure idempotent naming and collision avoidance (`storage/uploads/{hash}{ext}`).
   - Verified existence of `storage/uploads/.gitkeep`.

3. **Text Extraction & Chunking Services (`src/services/extractor.py` & `src/services/chunker.py`)**
   - Multi-format text extraction supporting UTF-8 source code (`.py`), Markdown (`.md`), plain text (`.txt`), and page-by-page PDF extraction using `pypdf`.
   - Sliding-window text chunker (`chunk_text`) with configurable `chunk_size` (default 500 characters) and `chunk_overlap` (default 50 characters).
   - Character offset tracking (`start_offset`, `end_offset`, `index`) returning discrete `TextChunk` records.

4. **Multipart File Ingestion Endpoint & Background Task Lifecycle**
   - Implemented `POST /api/v1/documents/upload` accepting multipart file binaries and `project_id`.
   - Automatic database registration of `Document` record with file size, storage URI, and MIME type.
   - Enqueued `ProcessingJob` with status `PENDING`.
   - Dispatched asynchronous FastAPI `BackgroundTask` (`process_document_background`) that transitions `ProcessingJob` to `IN_PROGRESS`, extracts text, chunks content, and transitions to `COMPLETED` or `FAILED` on error.
   - Specific exception handlers returning HTTP 413 for oversized files (`FileTooLargeError`) and HTTP 400 for unsupported formats (`UnsupportedFileExtensionError`).

5. **Pytest Integration Coverage (`tests/test_ingestion.py`)**
   - Sliding-window boundary offsets and overlapping continuity verification.
   - Edge case handling (empty strings, single small chunks, invalid parameter validation).
   - End-to-end file upload and background chunking completion for text/markdown files.
   - End-to-end PDF upload and page extraction completion.
   - HTTP 413 rejection verification for oversized files.
   - HTTP 400 rejection verification for unsupported extensions.
   - HTTP 404 rejection verification for non-existent projects.

---

### Week 1 — Backend Foundation (Completed)

1. **Modular FastAPI Application Architecture**
   - Core scaffolding (`src/core/`, `src/models/`, `src/schemas/`, `src/api/v1/`).
   - Lifespan management with graceful async engine disposal and CORS middleware.
2. **Async Database Infrastructure**
   - Native SQLAlchemy 2.0 async engine and session factory supporting PostgreSQL (`asyncpg`) and SQLite (`aiosqlite`).
   - Scoped `get_db` and `get_session_factory` transaction dependencies.
   - Asynchronous Alembic migration setup (`alembic/`).
3. **Domain Models**
   - `Project`, `Document`, and `ProcessingJob` with UUID primary keys and timezone-aware timestamps.
4. **Pydantic v2 Validation**
   - Strict schemas with `from_attributes=True` and standardized pagination.
5. **Initial Test Suite**
   - 15 integration tests covering health, project CRUD, document CRUD, and job state transitions.

---

## Next Steps (Week 5 — Search Quality)

1. **Hybrid Retrieval**:
   - Combine dense vector embeddings with sparse lexical search (e.g. BM25 / PostgreSQL full-text search).
   - Reciprocal Rank Fusion (RRF) for merging dense and sparse ranking scores.
2. **Cross-Encoder Reranking**:
   - Two-stage retrieval pipeline using cross-encoder models for deep semantic relevance scoring.
3. **Automated Search Quality Evaluation**:
   - CI-automated benchmark runner with regression guards on Recall@k and MRR thresholds.
