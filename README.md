# DevPilot

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%20(async)-red?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev)
[![Tested with Pytest](https://img.shields.io/badge/Pytest-Asyncio-0A9EDC?logo=pytest&logoColor=white)](https://pytest.org)

DevPilot is an AI-assisted development knowledge repository, document intelligence platform, and background processing engine. It provides high-performance asynchronous API services for managing projects, ingesting multi-format technical documents (Markdown, Python, Text, PDF), partitioning documents with overlapping text chunkers, and orchestrating asynchronous processing pipelines.

---

## Key Features

- **Asynchronous Architecture:** Built on FastAPI with fully non-blocking asynchronous execution.
- **SQLAlchemy 2.0 ORM:** Modern type-annotated models (`Mapped`, `mapped_column`) with UUID primary keys and timezone-aware timestamps.
- **Dual-Database Support:** Zero-install local development using async SQLite (`aiosqlite`), with direct drop-in production support for PostgreSQL (`asyncpg`).
- **Alembic Database Migrations:** Fully asynchronous migration pipeline.
- **Document Ingestion & Storage:** Async binary storage service with SHA-256 content deduplication, MIME & extension validation, and configurable size bounds.
- **Text Extraction & Chunking:** Multi-format document parser (Text, Markdown, Python, and PDF via `pypdf`) with sliding-window chunking.
- **Background Job Pipeline:** Real-time job lifecycle tracking (`PENDING` -> `IN_PROGRESS` -> `COMPLETED`/`FAILED`) using FastAPI `BackgroundTasks`.
- **Pydantic v2 Strict Validation:** Data contract validation, pagination schemas, and automatic ORM model serialization.
- **Comprehensive Pytest Suite:** Integration tests using `httpx.AsyncClient` with isolated database fixtures.

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/), [Starlette](https://www.starlette.io/), [Uvicorn](https://www.uvicorn.org/) |
| **Data Validation** | [Pydantic v2](https://docs.pydantic.dev/), `pydantic-settings` |
| **ORM & Database** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (async), [Asyncpg](https://github.com/MagicStack/asyncpg), [AioSQLite](https://github.com/omnilib/aiosqlite) |
| **Database Migrations** | [Alembic](https://alembic.sqlalchemy.org/) (Async Engine) |
| **File I/O & Ingestion** | `python-multipart`, `aiofiles`, `pypdf` |
| **Testing & Quality** | [Pytest](https://pytest.org/), `pytest-asyncio`, [HTTPX](https://www.python-httpx.org/) |

---

## Project Structure

```text
e:\Devpilot\
├── .env.example                      # Template environment configuration (SQLite / PostgreSQL)
├── .gitignore                         # Git exclusion rules
├── DEV_RULES.md                       # Architectural constraints & rules
├── STATUS.md                          # Project deliverables and milestone tracker
├── README.md                          # Project documentation
├── pyproject.toml                     # Project metadata and tool configuration
├── requirements.txt                   # Production dependencies
├── requirements-dev.txt               # Testing and development dependencies
├── alembic.ini                        # Alembic migration configuration
├── alembic/
│   ├── env.py                         # Async Alembic execution environment
│   ├── script.py.mako                 # Migration script template
│   └── versions/                      # Migration revisions directory
│       └── .gitkeep
├── src/
│   ├── __init__.py
│   ├── main.py                        # FastAPI application entrypoint and lifespan manager
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # Pydantic-settings BaseSettings
│   │   ├── database.py                # AsyncEngine, async_sessionmaker, get_db dependency
│   │   └── exceptions.py              # Domain exceptions and exception handlers
│   ├── models/
│   │   ├── __init__.py                # Model registry and Base export
│   │   ├── base.py                    # Base declarative model, UUID & timestamp mixins
│   │   ├── project.py                 # Project entity
│   │   ├── document.py                # Document entity
│   │   └── processing_job.py          # ProcessingJob entity & JobStatus enum
│   ├── schemas/
│   │   ├── __init__.py                # Schema registry
│   │   ├── common.py                  # BaseSchema, pagination models
│   │   ├── project.py                 # Project schemas
│   │   ├── document.py                # Document schemas
│   │   └── processing_job.py          # ProcessingJob schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── storage.py                 # Async LocalStorageService (SHA-256, validation)
│   │   ├── extractor.py               # Document text extraction (Text, MD, Py, PDF)
│   │   └── chunker.py                 # Sliding-window text chunker
│   └── api/
│       ├── __init__.py
│       └── v1/
│           ├── __init__.py
│           ├── api.py                 # v1 router aggregator
│           └── endpoints/
│               ├── __init__.py
│               ├── health.py          # Health check probe with live DB ping
│               ├── projects.py        # Project CRUD endpoints
│               ├── documents.py       # Document CRUD & multipart file upload
│               └── jobs.py            # Processing job status & polling endpoints
├── storage/
│   └── uploads/                       # Ingested file binary storage
│       └── .gitkeep
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Test fixtures with in-memory DB & AsyncClient
    ├── test_health.py                 # Health and root probe tests
    ├── test_projects.py               # Project CRUD integration tests
    ├── test_documents.py              # Document CRUD integration tests
    ├── test_jobs.py                   # ProcessingJob lifecycle integration tests
    └── test_ingestion.py              # Document upload & ingestion pipeline tests
```

---

## Getting Started

### 1. Prerequisites
- **Python 3.11+** installed (tested on Python 3.13)
- Windows PowerShell (or Bash on Linux/macOS)

### 2. Virtual Environment Setup

Open Windows PowerShell in the project root:

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements-dev.txt
```

### 3. Environment Configuration

Copy `.env.example` to create your local `.env`:

```powershell
Copy-Item .env.example .env
```

By default, `.env` is configured for zero-install local SQLite:
```ini
DATABASE_URL=sqlite+aiosqlite:///./devpilot.db
```

For production PostgreSQL, configure:
```ini
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/devpilot
```

### 4. Database Migrations (Alembic)

Run migrations to synchronize database schemas:

```powershell
# Apply existing migrations
.\.venv\Scripts\alembic.exe upgrade head

# Generate a new migration after model changes
.\.venv\Scripts\alembic.exe revision --autogenerate -m "describe_changes"
```

### 5. Running the Application

Launch the development server with live reload:

```powershell
.\.venv\Scripts\uvicorn.exe src.main:app --reload --host 127.0.0.1 --port 8000
```

Once running:
- **API Base:** `http://127.0.0.1:8000/`
- **Interactive Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc Documentation:** `http://127.0.0.1:8000/redoc`
- **Health Probe:** `http://127.0.0.1:8000/api/v1/health`

---

## Running Tests

Execute the complete integration test suite with `pytest`:

```powershell
.\.venv\Scripts\pytest.exe -v
```

All integration tests utilize isolated in-memory SQLite transactions and `httpx.AsyncClient` with zero external service dependencies.
