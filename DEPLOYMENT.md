# DevPilot Deployment & Evaluation Guide

This guide details deployment options, database migrations, automated demo data seeding, the one-click fallback runner, and the secure read-only demo evaluation mode for DevPilot.

---

## 1. Quickstart Deployment Options

### Option A: One-Click Local Fallback Demo Runner (Fastest & Simplest)
For instant evaluation with zero setup friction, DevPilot provides a unified one-click runner that automatically checks the environment, verifies `.env`, applies Alembic migrations, seeds sample documents, and launches the server with ready-to-test curl commands.

**Cross-Platform (Python):**
```bash
python scripts/run_local_demo.py
```

**Windows (.bat shortcut):**
```cmd
run_demo.bat
```

**Linux / macOS (Shell script):**
```bash
chmod +x run_demo.sh
./run_demo.sh
```

**Runner Flags:**
- `--no-server`: Runs setup, migrations, and seeding, prints verification commands, and exits without launching the Uvicorn server (ideal for headless CI/CD).
- `--force-reseed`: Re-seeds the demo workspace even if already present.
- `--port PORT`: Specifies custom HTTP port (default: `8000`).
- `--host HOST`: Specifies bind host (default: `127.0.0.1`).

---

### Option B: Docker Compose Container Deployment
DevPilot provides a multi-stage production container setup with persistent volume mapping for SQLite, uploaded assets, and benchmark artifacts.

```bash
# 1. Build and start application container in detached mode
docker compose up --build -d

# 2. Verify container service health check
curl http://localhost:8000/api/v1/health

# 3. Seed demo workspace and sample documents inside container
docker compose exec app python scripts/seed_demo.py

# 4. View container logs
docker compose logs -f app

# 5. Stop container services
docker compose down
```

---

### Option C: Manual Virtual Environment Setup
```bash
# 1. Clone repository and create virtual environment
python -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# .\.venv\Scripts\Activate.ps1  # On Windows PowerShell

# 2. Install dependencies (editable mode)
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .

# 3. Configure environment file
cp .env.example .env

# 4. Run database migrations
alembic upgrade head

# 5. Seed sample demo workspace and documents
python scripts/seed_demo.py

# 6. Launch Uvicorn server
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 2. Automated Sample Data Seeding

DevPilot includes an automated seeding script ([`scripts/seed_demo.py`](scripts/seed_demo.py)) to instantly provision an evaluation workspace with pre-indexed technical documents.

### Seeding Command:
```bash
python scripts/seed_demo.py
```

### Options:
- `--project-name`: Custom name for demo workspace (default: `"DevPilot Evaluation Workspace"`).
- `--api-key`: Tenant identifier / API key for demo access (default: `"devpilot-demo-key"`).
- `--force`: Force re-creation and re-indexing of documents even if they already exist.

### Seeded Documents:
1. **`architecture_overview.md`**: High-level system architecture, FastAPI asynchronous concurrency, sliding-window chunking (512c, 64c overlap), dense/sparse retrieval pipeline, and cross-encoder consensus.
2. **`api_reference.md`**: REST API endpoints, tenant isolation security model, processing jobs lifecycle, and citation verification guardrails.
3. **`multilingual_capabilities.md`**: Multi-script support covering English, Bengali native script (`[\u0980-\u09ff]`), and Romanized Banglish.

---

## 3. Read-Only Demo Mode & Safe Credentials

To allow judges, evaluators, and auditors to safely explore and benchmark DevPilot without altering state or risking data corruption, a dedicated **Read-Only Demo Mode** is built directly into the authentication layer and middleware.

### Demo Credentials:
- **Demo API Key:** `demo-readonly-key` (or configured via environment variable `DEMO_API_KEY`)
- **Header:** `X-API-Key: demo-readonly-key`
- **Toggle Setting:** `DEMO_MODE=true` (enabled by default)

### Permissions Matrix:

| Action / Endpoint | HTTP Method | Demo Access | Behavior / HTTP Code |
| :--- | :---: | :---: | :--- |
| **Service Health Check** (`/api/v1/health`) | `GET` | ✅ Allowed | 200 OK |
| **List & Inspect Projects** (`/api/v1/projects`, `/api/v1/projects/{id}`) | `GET` | ✅ Allowed | 200 OK (Access to demo evaluation workspace) |
| **List & View Documents** (`/api/v1/documents`, `/api/v1/documents/{id}`) | `GET` | ✅ Allowed | 200 OK |
| **Semantic & Hybrid Search** (`/api/v1/projects/{id}/search`) | `POST` | ✅ Allowed | 200 OK (Vector cosine similarity, BM25, RRF) |
| **Grounded RAG Synthesis** (`/api/v1/projects/{id}/rag`) | `POST` | ✅ Allowed | 200 OK (Answer generation + citation verification) |
| **Bounded Agent Workflow** (`/api/v1/projects/{id}/agent/workflow`) | `POST` | ✅ Allowed | 200 OK (4-phase FSM audit report) |
| **Poll Processing Jobs** (`/api/v1/jobs`, `/api/v1/jobs/{id}`) | `GET` | ✅ Allowed | 200 OK |
| **Create Project** (`/api/v1/projects`) | `POST` | ❌ Blocked | 403 Forbidden (Write mutations disabled in Demo Mode) |
| **Update Project** (`/api/v1/projects/{id}`) | `PATCH` | ❌ Blocked | 403 Forbidden |
| **Delete Project** (`/api/v1/projects/{id}`) | `DELETE` | ❌ Blocked | 403 Forbidden |
| **Upload Document** (`/api/v1/documents/upload`) | `POST` | ❌ Blocked | 403 Forbidden |
| **Update / Delete Document** (`/api/v1/documents/{id}`) | `PATCH`/`DELETE` | ❌ Blocked | 403 Forbidden |
| **Access Other Tenant Workspace** | Any | ❌ Blocked | 403 Forbidden (Tenant boundary enforcement) |

---

## 4. Evaluator Verification Commands (`cURL`)

Evaluators can execute these sample queries against a running instance (`http://127.0.0.1:8000`) using the read-only credentials:

### 1. Service Health Check
```bash
curl http://127.0.0.1:8000/api/v1/health
```

### 2. List Seeded Evaluation Projects
```bash
curl http://127.0.0.1:8000/api/v1/projects \
  -H "X-API-Key: demo-readonly-key"
```

### 3. Grounded RAG Query with Citation Provenance
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/c651c832-a5cc-473a-abff-76f08e5e1b5f/rag \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the architecture of DevPilot?"}'
```

### 4. Hybrid Semantic & Lexical Search
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/c651c832-a5cc-473a-abff-76f08e5e1b5f/search \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "hybrid consensus reranker", "mode": "hybrid", "top_k": 3}'
```

### 5. Bounded Agentic Workflow (4-Phase FSM)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/c651c832-a5cc-473a-abff-76f08e5e1b5f/agent/workflow \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"task": "Analyze DevPilot multi-tenant security architecture"}'
```

### 6. Verify Write Mutation Guard (Expect HTTP 403 Forbidden)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "Unauthorized Mutation Project"}'
```

---

## 5. Offline Automated Verification

```bash
# 1. Run static analysis with Ruff
ruff check src/ tests/ scripts/

# 2. Run automated test suite (86/86 passing)
pytest -v

# 3. Execute multilingual retrieval benchmark sweep
python -m src.evaluation.runner --top-k 3 --mock-llm
```
