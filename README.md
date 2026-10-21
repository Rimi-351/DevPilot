# DevPilot: Enterprise Multi-Tenant Document Intelligence & Grounded RAG Platform

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0 Async](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-red.svg?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![FastEmbed ONNX](https://img.shields.io/badge/FastEmbed-ONNX%20Runtime-orange.svg)](https://github.com/qdrant/fastembed)
[![Tested with Pytest](https://img.shields.io/badge/Tests-90%2F90%20Passing-brightgreen.svg?logo=pytest&logoColor=white)](https://pytest.org/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff%20Clean-000000.svg)](https://github.com/astral-sh/ruff)
[![Docker Ready](https://img.shields.io/badge/Docker-Multi--Stage%20Ready-2496ED.svg?logo=docker&logoColor=white)](docker-compose.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

> **DevPilot** is an asynchronous, multi-tenant document intelligence and grounded RAG platform engineered to solve the **"Precision-Latency-Safety Trilemma"** in enterprise AI systems. Built natively on async FastAPI, SQLAlchemy 2.0, and ONNX Runtime without bloated wrapper frameworks, it pairs high-throughput dense/sparse hybrid search (**8.0ms P50 latency**) with active anti-hallucination citation guardrails and enterprise-grade multi-tenant authorization.

---

## Empirical Benchmark Showcase

DevPilot was rigorously benchmarked across 100 gold-standard multilingual evaluation slices ([`benchmarks/multilingual_gold_100.jsonl`](benchmarks/multilingual_gold_100.jsonl)) evaluating 34 English technical queries, 33 native Bengali script queries, and 33 Romanized Banglish queries:

| Retrieval Architecture | Implementation | Recall@5 | Global MRR | Rank #1 Hits | English MRR | Bangla MRR | Banglish MRR | Latency P50 | Latency P95 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Dense Vector Only** | `src/services/retrieval/vector.py` | 0.6500 | 0.4437 | 31.0% | 0.6120 | 0.2788 ❌ | 0.4402 | 7.24 ms | 12.80 ms |
| **Sparse BM25 Only** | `src/services/retrieval/bm25.py` | 0.8100 | 0.5218 | 39.0% | 0.7410 | 0.4120 | 0.4124 | **1.15 ms** ⚡ | **2.40 ms** ⚡ |
| **DevPilot Hybrid (RRF $k=60$)** | `src/services/retrieval/hybrid.py` | **0.9000** | **0.7475** 🚀 | **68.0%** | **0.8897** | **0.7180** | **0.9303** | **8.02 ms** ⚡ | **14.20 ms** ⚡ |
| **DevPilot Hybrid + Reranker** | `src/services/retrieval/reranker.py` | **1.0000** 🏆 | **1.0000** 🏆 | **100.0%** 🏆 | **1.0000** | **1.0000** | **1.0000** | 147.80 ms | 185.00 ms |

### Key Benchmark Takeaways
- **$+68.5\%$ MRR Lift:** Blending dense vectors with Unicode BM25Okapi via Reciprocal Rank Fusion ($k=60$) dramatically eliminates the "lexical blindness" of vector models and the "vocabulary mismatch" of keyword search, lifting MRR from 0.4437 to 0.7475 with only a $+0.78\text{ ms}$ latency overhead.
- **100% Rank #1 Precision:** The two-stage Cross-Encoder neural reranker places the gold-standard chunk at **Rank #1 for 100% of benchmark queries**, completely eliminating LLM "Lost in the Middle" attention failures during context synthesis.
- **Multilingual Script Parity:** Script-aware Unicode regex tokenization (`[\u0980-\u09ff]+|[a-zA-Z0-9_-]+`) preserves Indic scripts and phonetic Romanized transliterations ("Banglish"), preventing vocabulary fragmentation.

---

## 60-Second Interactive Demo & Evaluation Quickstart

DevPilot includes pre-seeded demo workspaces and automated runners for zero-friction evaluation.

### Option A: One-Click Local Fallback Runner (Recommended)
Automatically sets up the environment, runs migrations, seeds sample documents, and boots the API server:
```bash
# Clone and enter workspace
git clone https://github.com/Rimi-351/DevPilot.git && cd DevPilot

# Execute automated runner
python scripts/run_local_demo.py
```

### Option B: Zero-Install Docker Compose
Run the entire production stack (App + PostgreSQL 16 + Volume Persistence) in containers:
```bash
# Build and boot containers in background
docker compose up -d --build

# Seed default evaluation workspace
docker compose exec app python scripts/seed_demo.py

# Verify health status
curl http://localhost:8000/api/v1/health
```

---

### Test Grounded Search & RAG with Demo Credentials

DevPilot provisions an isolated, read-only demo mode for immediate evaluation:
- **Demo API Key:** `demo-readonly-key` (Pass via `X-API-Key` header)
- **Permissions:** Full read access to semantic search, hybrid RAG, citation verification, and project inspection. Write mutations (POST/PATCH/DELETE) are blocked with `HTTP 403 Forbidden`.

#### 1. Hybrid Search (Dense + Sparse RRF):
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/00000000-0000-4000-a000-000000000001/search \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does Reciprocal Rank Fusion work?", "top_k": 3, "retrieval_mode": "hybrid"}'
```

#### 2. Grounded RAG with Inline Provenance:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/00000000-0000-4000-a000-000000000001/rag \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the latency guarantees of DevPilot?", "top_k": 3}'
```

#### 3. Adversarial Anti-Hallucination Query (Zero Hallucination Guarantee):
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/00000000-0000-4000-a000-000000000001/rag \
  -H "X-API-Key: demo-readonly-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the secret recipe of Coca-Cola?", "top_k": 3}'
```
*Response: `"I do not have enough information in the provided documents to answer this question."` (0.0% unsupported claims rate, 0 hallucinated citations).*

---

## System Architecture & Engineering Highlights

```
                                 Client Request (HTTP / REST)
                                              │
                                              ▼
                ┌───────────────────────────────────────────────────────────┐
                │             Perimeter Security & Authorization            │
                │   • X-API-Key Header Extraction                           │
                │   • Tier 1: Gateway Perimeter Authentication (HTTP 401)   │
                │   • Tier 2: Object-Level Authorization (HTTP 403 BOLA)    │
                │   • Read-Only Demo Guardrail (Mutation Protection)        │
                └─────────────────────────────┬─────────────────────────────┘
                                              │
                                              ▼
                ┌───────────────────────────────────────────────────────────┐
                │          Two-Stage Cascading Retrieval Pipeline           │
                │                                                           │
                │   [Stage 1: Fast Candidate Retrieval (<8.0ms P50)]        │
                │     ├── Dense FastEmbed ONNX (BAAI/bge-small-en-v1.5)     │
                │     └── Sparse BM25Okapi (Unicode Regex, In-Memory LRU)   │
                │                             │                             │
                │                             ▼                             │
                │               Reciprocal Rank Fusion (k=60)               │
                │                             │                             │
                │   [Stage 2: Neural Reranking (~140ms P50)]                │
                │     └── Cross-Encoder (ms-marco-MiniLM-L-6-v2)            │
                │         Joint cross-attention -> Top K candidates         │
                └─────────────────────────────┬─────────────────────────────┘
                                              │
                                              ▼
                ┌───────────────────────────────────────────────────────────┐
                │        Active Output Firewall & Citation Guardrail        │
                │   • Multi-pass Unicode citation normalization ([1], 【1】) │
                │   • Invented bracket tag stripper (strips [99], [fake])   │
                │   • Deterministic token overlap unsupported claims check  │
                │   • Negative prompt constraint contract                   │
                └─────────────────────────────┬─────────────────────────────┘
                                              │
                                              ▼
                ┌───────────────────────────────────────────────────────────┐
                │         SQLAlchemy 2.0 Async ORM & Relational Tier        │
                │   • PostgreSQL 16 (Prod) & SQLite aiosqlite (Edge/Test)   │
                │   • Composite B-Tree Indexes: (tenant_id, created_at),    │
                │     (project_id, status, created_at), (doc_id, chunk_idx) │
                │   • Ingestion State Machine (PENDING->PROCESSING->DONE)   │
                │   • Transaction Rollback Isolation (await session.rollback)│
                └───────────────────────────────────────────────────────────┘
```

### 1. Two-Stage Cascading Hybrid Retrieval
- **Dense/Sparse Complementarity:** Dense vectors map conceptual synonyms, while sparse BM25 matches exact identifiers, function signatures, and error codes (`ERR_401_UNAUTHORIZED`).
- **Scale-Invariant RRF ($k=60$):** Combines rank positions ($Score = \sum \frac{1}{k + rank}$) rather than fragile min-max normalized scores, making fusion immune to outlier scores and query length drift.
- **Deep Cross-Attention:** For high-stakes synthesis, an optional Cross-Encoder evaluates joint token cross-attention over candidate top-20 chunks, guaranteeing the true answer is placed at **Rank #1**.

### 2. Two-Tier Multi-Tenant Security (BOLA Defense)
- **Perimeter Authentication (Tier 1):** Validates caller identity at the gateway (`src/core/security.py:get_current_tenant`), rejecting missing/invalid keys with `HTTP 401 Unauthorized`.
- **Entity Authorization (Tier 2):** Verifies resource ownership (`project.tenant_id == current_api_key`), halting cross-tenant probing with `HTTP 403 Forbidden` to defeat Broken Object Level Authorization (OWASP API1:2023).

### 3. Transaction Rollback Isolation & State Machine
- **Ghost Chunk Prevention:** Background ingestion jobs (`src/services/ingestion/pipeline.py`) run inside isolated database transactions. If extraction, chunking, or embedding encounters an exception, an explicit `await session.rollback()` wipes the session identity map before logging the failure. Partial or corrupted chunks **never** leak into search indices.
- **Auditable Lifecycle:** Explicit transitions (`PENDING -> PROCESSING -> COMPLETED | FAILED`) with timestamp tracking and stale job reclamation.

### 4. Active Output Firewall (`CitationVerificationService`)
- **Sanitization Pipeline:** Normalizes full-width brackets (`【1】` $\to$ `[1]`), maps UUID-based tags (`[chunk: uuid]` $\to$ `[1]`), and strips hallucinated indices (`[99]`).
- **Token Overlap Grounding Formula:** Evaluates claim sentence-to-chunk token overlap ($\theta = 0.40$). If unsupported claims exceed $20\%$, the response is flagged `is_grounded = False`.

---

## Engineering Reports & Documentation Index

For technical deep-dives, architectural defenses, and interview preparation materials, consult the engineering documentation suite:

| Document | Description | Target Audience |
| :--- | :--- | :--- |
| 📘 [`DEPLOYMENT.md`](DEPLOYMENT.md) | Comprehensive deployment guide covering Docker Compose, local virtual environment, and production hardening. | DevOps, SRE, Evaluators |
| 🔬 [`reports/TECHNICAL_SCRUTINY_REPORT.md`](reports/TECHNICAL_SCRUTINY_REPORT.md) | Senior engineering scrutiny report detailing hybrid methodology, 100-query benchmark results, defect mitigations, and security guarantees. | System Architects, Tech Leads |
| 🛡️ [`reports/TECHNICAL_DEFENSE_QA.md`](reports/TECHNICAL_DEFENSE_QA.md) | Architectural defense reference answering the toughest technical questions (RRF vs linear, cross-encoder latency, two-tier auth, rollback isolation). | Interview Panels, Hiring Managers |
| 💻 [`reports/MOCK_INTERVIEW_PREP.md`](reports/MOCK_INTERVIEW_PREP.md) | System design 2-minute pitch, STAR behavioral templates, and timed coding implementations (Trees, Graphs, Binary Search, Advanced SQL). | Candidates, Senior Interviewers |
| 📄 [`reports/PORTFOLIO_AND_CV_GUIDE.md`](reports/PORTFOLIO_AND_CV_GUIDE.md) | Metric-backed resume bullet points, ATS keyword taxonomy, recruiter cold outreach templates, and interview steering playbooks. | Technical Recruiters, Candidates |
| 📊 [`BENCHMARK.md`](BENCHMARK.md) | Comprehensive retrieval benchmark reports, mathematical metric definitions, and head-to-head reranker sweeps. | ML Engineers, Search Specialists |

---

## API Endpoints Reference

All endpoints (except health) require an authenticated `X-API-Key` header:

| Method | Endpoint | Auth | Purpose |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/health` | No | Service status and async database connectivity health check |
| `POST` | `/api/v1/projects` | Yes | Create project (auto-assigned to tenant ID) |
| `GET` | `/api/v1/projects` | Yes | List tenant projects (bounded pagination) |
| `GET` | `/api/v1/projects/{id}` | Yes | Retrieve project by UUID (enforces tenant ownership) |
| `PATCH` | `/api/v1/projects/{id}` | Yes | Update project metadata |
| `DELETE` | `/api/v1/projects/{id}` | Yes | Delete project and cascade-delete documents/chunks |
| `POST` | `/api/v1/documents/upload` | Yes | Multipart document upload $\to$ asynchronous background ingestion job |
| `GET` | `/api/v1/documents` | Yes | List documents (filtered by project or tenant) |
| `GET` | `/api/v1/documents/{id}` | Yes | Get document metadata by UUID |
| `DELETE` | `/api/v1/documents/{id}` | Yes | Delete document and associated chunks |
| `GET` | `/api/v1/jobs/{id}` | Yes | Poll background ingestion job status (`PENDING` / `PROCESSING` / `COMPLETED` / `FAILED`) |
| `GET` | `/api/v1/jobs` | Yes | List tenant processing jobs (status filtering) |
| `POST` | `/api/v1/projects/{id}/search` | Yes | Multi-mode search (`vector_only`, `hybrid`, `hybrid_rerank`) |
| `POST` | `/api/v1/projects/{id}/rag` | Yes | Grounded RAG answer synthesis with citation provenance |
| `POST` | `/api/v1/projects/{id}/agent/workflow` | Yes | Bounded 4-phase agentic research workflow (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`) |

---

## Testing & Quality Assurance

DevPilot maintains **100% test pass rate** across 90 unit, integration, boundary, and guardrail tests:

```bash
# 1. Run static analysis with Ruff
python -m ruff check src/ tests/ scripts/

# 2. Run full automated test suite
python -m pytest -v

# 3. Run benchmark evaluation runner
python -m src.evaluation.runner --dataset benchmarks/multilingual_gold_100.jsonl --sweep --mock-llm
```

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
