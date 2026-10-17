# DevPilot Project Status

**Current Target:** Week 4 — RAG & Evaluation  
**Status:** Week 3 Completed  
**Last Verified:** With `pytest` (27/27 integration tests passing, 0 warnings)  

---

## Completed Deliverables

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

## Next Steps (Week 4 — RAG & Evaluation)

1. **Context Construction & Grounded Prompt Assembly**:
   - Aggregate top-k retrieved chunks formatted with provenance citations.
   - Assemble context windows with token limit management.
2. **LLM Generation Pipeline**:
   - Async interface to LLM provider (e.g. OpenAI / Gemini / local Ollama) for grounded answer synthesis.
   - Strict citation enforcement linking claims directly to chunk IDs and file offsets.
3. **Evaluation Benchmarks**:
   - Establish benchmark dataset and automated retrieval/grounding evaluation harness.
