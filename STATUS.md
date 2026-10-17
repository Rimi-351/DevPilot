# DevPilot Project Status

**Current Target:** Week 2 — Document Ingestion Pipeline  
**Status:** Completed  
**Last Verified:** With `pytest` (22/22 integration tests passing, 0 warnings)  

---

## Completed Deliverables

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
   - Dispatched asynchronous FastAPI `BackgroundTask` (`process_document_background`) that transitions `ProcessingJob` to `IN_PROGRESS`, extracts text, chunks content, and transitions to `COMPLETED` (logging chunk count and total characters) or `FAILED` on error.
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

## Next Steps (Week 3 — Embeddings & Vector Search)

1. **Vector Embedding Pipeline**:
   - Integrate embedding generation service (e.g. sentence-transformers, OpenAI/Vertex AI embeddings).
   - Generate vector representations for each text chunk produced by the ingestion pipeline.
2. **Vector Store Integration**:
   - Evaluate and integrate vector storage (e.g. pgvector for PostgreSQL or local FAISS/Chroma).
3. **Semantic Search Endpoints**:
   - `POST /api/v1/search`: Query semantic similarity across indexed document chunks within a project.
