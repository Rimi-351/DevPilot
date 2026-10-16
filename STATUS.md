# DevPilot Project Status

**Current Target:** Week 1 — Backend Foundation  
**Status:** Completed  
**Last Verified:** With `pytest` (15/15 integration tests passing)  

---

## Completed Deliverables (Week 1)

### 1. Modular Application Architecture
- Scaffolding of core directories:
  - `src/core/`: Application settings via `pydantic-settings`, SQLAlchemy 2.0 async engine and sessionmaker with connection pooling, and domain exceptions.
  - `src/models/`: Declarative ORM models built with modern SQLAlchemy 2.0 `Mapped` and `mapped_column` type annotations.
  - `src/schemas/`: Pydantic v2 schemas using `ConfigDict(from_attributes=True)` and strict validations.
  - `src/api/v1/`: Versioned API router structure isolating business endpoints.
- Main entrypoint `src/main.py` with asynchronous lifespan manager and global exception handlers.

### 2. Async Database Infrastructure (SQLAlchemy 2.0 & PostgreSQL)
- Asynchronous session management with `async_sessionmaker(expire_on_commit=False)` and resilient connection pool configurations (`pool_pre_ping=True`).
- `get_db` dependency providing scoped transaction management with automatic rollback on unhandled exceptions.
- Alembic configuration (`alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`) wired for async migrations using `Base.metadata`.

### 3. Initial Domain Models
- **`Project`** (`src/models/project.py`):
  - UUID primary key, timezone-aware `created_at` and `updated_at` timestamps.
  - Indexed `name`, optional `description`.
  - Cascading one-to-many relationships to `Document` and `ProcessingJob`.
- **`Document`** (`src/models/document.py`):
  - UUID primary key, foreign key link to `Project` (`ondelete="CASCADE"`).
  - Storage location (`file_path`), MIME type (`file_type`), file size (`file_size_bytes`).
  - Cascading one-to-many relationship to `ProcessingJob`.
- **`ProcessingJob`** (`src/models/processing_job.py`):
  - State machine tracking via `JobStatus` enum (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`).
  - Associated `project_id` and optional `document_id`.
  - JSON payload input and result output containers, error message logging.

### 4. Pydantic v2 Schemas & Validation
- Standardized `PaginationParams` and generic `PaginatedResponse[T]`.
- Strict request models (`ProjectCreate`, `ProjectUpdate`, `DocumentCreate`, `DocumentUpdate`, `ProcessingJobCreate`, `ProcessingJobUpdate`).
- Response models (`ProjectRead`, `DocumentRead`, `ProcessingJobRead`) with automatic ORM conversion.

### 5. Integration Test Suite (`tests/`)
- Pytest integration suite using `pytest-asyncio` and `httpx.AsyncClient` with `ASGITransport`.
- Isolated in-memory async SQLite engine fixture overriding `get_db` dependency without mocking API logic.
- 100% test pass rate across 15 tests:
  - `tests/test_health.py` (2 tests: root and health probe)
  - `tests/test_projects.py` (6 tests: full CRUD, pagination, 404 handling, 422 validation)
  - `tests/test_documents.py` (4 tests: creation, project FK validation, filtering, deletion)
  - `tests/test_jobs.py` (3 tests: job status lifecycle, project FK validation, status filtering)

---

## Next Steps (Week 2 — Ingestion & Processing Pipeline)

1. **File Storage & Ingestion Service**:
   - Implement storage provider interface (local disk / S3 compatible) for document uploads.
   - Multipart file upload endpoints in `/api/v1/documents/upload`.
2. **Background Worker / Task Queue Integration**:
   - Evaluate lightweight async background workers (or Redis / Celery / ARQ) to process `ProcessingJob` queues.
3. **Document Parsing & Text Extraction**:
   - Handlers for markdown, PDF, and code files.
