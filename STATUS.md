# DevPilot Project Status

**Current Target:** Week 6 — Bounded Agentic Workflows with Tool Calling & Structured Outputs  
**Status:** **Weeks 1–6 COMPLETE** — Full Platform Built, Secured, Tested, Benchmarked & Agentic Workflows Live  
**Last Verified:** `pytest -v` → **54/54 integration tests passing, 0 warnings**  
**CI / Docker:** Verified with GitHub Actions workflow and multi-stage Docker containers  

---

## Milestone Progress Overview

| Milestone | Deliverable Focus | Status | Test Coverage |
|:---|:---|:---:|:---:|
| **Week 1** | Async Foundation, SQLAlchemy 2.0 & REST API Structure | ✅ Complete | 7 tests |
| **Week 2** | Multipart Storage, Extractor Pipeline & Background Jobs | ✅ Complete | 11 tests |
| **Week 3** | Authentication, Cross-Tenant Isolation & Security Hardening | ✅ Complete | 3 tests (`test_auth.py`) |
| **Week 4** | Dense Vector Search (BGE-384) & Grounded RAG with Citations | ✅ Complete | 14 tests |
| **Week 5** | Hybrid Search (BM25+RRF), Cross-Encoder Reranker, 50-Query Benchmark & Docker/CI | ✅ Complete | 13 tests |
| **Week 6** | Bounded Agentic Workflows with Tool Calling & Structured Outputs | ✅ Complete | 6 tests (`test_agent.py`) |
| **Total** | **Comprehensive Full-Stack AI Platform** | **100% Green** | **54/54 Passing** |

---

## Completed Architecture Deliverables

### Week 6 — Bounded Agentic Workflows with Tool Calling & Structured Outputs (Completed)

1. **Agent Service Schemas (`src/services/agent/schemas.py`)**
   - Implemented `WorkflowPhase(str, Enum)`: `SEARCH`, `INSPECT`, `SUMMARIZE`, `PROPOSE`.
   - Strict runtime Pydantic v2 input schemas:
     - `SearchInput`: `query: str` (min 3 chars).
     - `InspectInput`: `chunk_id: str` (UUID or hex chunk ID validation).
     - `SummarizeInput`: `text: str` (min 20 chars).
   - Execution telemetry models: `ToolExecutionStatus` (`SUCCESS`, `VALIDATION_ERROR`, `TIMEOUT`, `EXECUTION_ERROR`, `PHASE_VIOLATION`), `ToolExecutionLog`.
   - Structured deliverable models: `AgentProposal` (title, executive summary, action items, confidence score 0.0–1.0) and `WorkflowReport` (status, total iterations, runtime, phase history, logs, final proposal).

2. **Real Data-Bound Agent Tools (`src/services/agent/tools.py`)**
   - `search_project(query, project_id, session)`: Executes Week 5 hybrid retrieval pipeline (`retrieve_chunks(search_mode="hybrid", top_k=5)`) scoped to target project.
   - `inspect_chunk(chunk_id, project_id, session)`: Direct lookup of full chunk text and metadata from `DocumentChunk` with project tenant boundaries.
   - `summarize_text(text)`: Distills key technical findings via `LLMService` with resilient extractive summarizer fallback.

3. **Guarded Tool Dispatcher & Bounded Agent (`src/services/agent/workflow.py`)**
   - `GuardedToolDispatcher`: Pure-async 4-layer runtime firewall:
     1. Phase boundary checking (`PHASE_VIOLATION`)
     2. Pydantic v2 argument validation (`VALIDATION_ERROR`)
     3. `asyncio.wait_for` timeout isolation (`TIMEOUT`, default 3.0s)
     4. Exception fallback blocks returning structured diagnostic error dictionaries into LLM context (`EXECUTION_ERROR`).
   - `BoundedAgent`:
     - Deterministic 4-phase finite state machine: `SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`.
     - Hard loop cap `MAX_ITERATIONS = 5`.
     - Contextual self-correction: failed tool calls reflect error details into context for prompt self-repair without crashing.
     - Structured JSON proposal synthesis in `PROPOSE` phase.

4. **Authenticated Agent Workflow Endpoint (`src/api/v1/endpoints/agent.py`)**
   - Route: `POST /api/v1/projects/{project_id}/agent/workflow`
   - Request: `AgentWorkflowRequest(goal: str)` (5–1000 characters).
   - Response: `WorkflowReport`.
   - Security: Enforces `X-API-Key` authentication (401), project existence (404), and tenant isolation via `verify_project_tenant_access` (403).

5. **Comprehensive Pytest Suite (`tests/test_agent.py`)**
   - 6 test cases verifying bounded progression, validation error reflection & self-correction, phase boundary protection, timeout isolation, loop cap termination, and authenticated API endpoint security.

### Week 5 — Search Quality, 50-Query Benchmark & Containerized CI (Completed)

1. **Hybrid Retrieval Pipeline & Reciprocal Rank Fusion (`src/services/retrieval/hybrid.py`)**
   - Implemented `bm25_search()` using `rank_bm25.BM25Okapi` with deterministic alphanumeric tokenization.
   - Implemented `reciprocal_rank_fusion(dense_results, sparse_results, k=60, top_n=10)` using standard RRF formula:
     $$\text{RRF\_Score}(d) = \sum \frac{1}{k + \text{rank} + 1}$$
   - Deduplicates candidate chunks by UUID while accumulating dense and sparse scores.

2. **In-Memory BM25 Index Caching**
   - Implemented `_bm25_cache: dict[str, tuple[int, BM25Okapi, list[dict]]]` keyed by project ID and corpus content hash.
   - Eliminates redundant tokenization across subsequent queries for the same project.

3. **Cross-Encoder Reranker (`src/services/retrieval/reranker.py`)**
   - Integrated `cross-encoder/ms-marco-MiniLM-L-6-v2` evaluating deep joint query-document cross-attention.
   - Added transparent fallback logging (`RERANKER_FALLBACK_ACTIVE`) and candidate metadata tagging (`reranker_applied`, `reranker_engine`).
   - Achieves **1.00 MRR** on the 50-query benchmark.

4. **50-Query Gold Standard & Parameter Sweep (`benchmarks/gold_standard_50.jsonl`, `src/evaluation/runner.py`)**
   - Built 50-item benchmark spanning 15 exact identifier queries, 15 conceptual paraphrases, 10 multi-chunk synthesis queries, and 10 out-of-scope negative constraint queries.
   - Implemented parameter sweep across `chunk_size=512` and `top_k \in [3, 5]` for `vector_only`, `hybrid`, and `hybrid_rerank`.
   - Formally defined `unsupported_claims_rate` metric with $0.40$ sentence-to-chunk token overlap ratio and negative constraint refusal support.
   - Persisted verified benchmark artifacts to `artifacts/benchmark_results.json`.

5. **Multi-Stage Docker & Container Deployability (`Dockerfile`, `docker-compose.yml`)**
   - Multi-stage build on `python:3.11-slim` with isolated builder stage, non-root user `devpilot` (UID 1000), healthcheck on port 8000, and `.dockerignore`.
   - `docker-compose.yml` configuring API service alongside PostgreSQL 16 Alpine with persisted volumes (`storage_data`, `artifacts_data`, `postgres_data`).

6. **Continuous Integration Workflow (`.github/workflows/ci.yml`)**
   - Triggers on push and pull request to `main`.
   - Executes syntax/linter verification with `ruff`, runs full test suite (`pytest -v`), executes benchmark evaluation (`python -m src.evaluation.runner --top-k 3`), and uploads benchmark artifacts.

---

### Week 3 — Authentication & Cross-Tenant Access Control (Completed)

1. **API Key Authentication (`src/core/security.py`)**
   - Implemented `get_current_api_key` utilizing `APIKeyHeader(name="X-API-Key", auto_error=False)`.
   - Returns `HTTP 401 Unauthorized` with `WWW-Authenticate: X-API-Key` on missing, empty, or whitespace keys.

2. **Project Tenant Ownership (`src/models/project.py`, `src/schemas/project.py`)**
   - Added `tenant_id` and `owner_api_key` indexed columns to `Project` ORM model.
   - Automatically populates caller's API key upon `POST /api/v1/projects`.
   - Surfaced `tenant_id` in `ProjectRead` schema.

3. **Tenant Isolation Enforcement**
   - `src/api/v1/endpoints/projects.py`: Queries filtered by tenant; CRUD operations verify tenant ownership, returning `HTTP 403 Forbidden` on mismatch.
   - `src/api/v1/endpoints/documents.py`: Upload, create, list, get, update, and delete endpoints enforce `api_key` dependency and verify project ownership.
   - `src/api/v1/endpoints/search.py` and `src/api/v1/endpoints/rag.py`: Guarded with `verify_project_tenant_access`.

4. **Automated Security Verification (`tests/test_auth.py`)**
   - `test_auth_missing_or_empty_key_returns_401`: Validates 401 on unauthenticated requests.
   - `test_auth_cross_tenant_access_returns_403`: Verifies Tenant B receives 403 Forbidden attempting to access, update, delete, ingest into, search, or run RAG on Tenant A's project.
   - `test_auth_valid_owner_lifecycle_success_200`: Verifies complete authorized tenant lifecycle (200/201/204).

---

### Week 4 — Grounded RAG & Semantic Vector Search (Completed)

1. **Dense Vector Embeddings (`src/services/embedding.py`)**
   - Asynchronous `EmbeddingService` running FastEmbed `BAAI/bge-small-en-v1.5` producing 384-dimensional dense vectors on ONNX Runtime CPU.
   - Built-in deterministic mock fallback for offline and CI testing.

2. **Grounded Answer Synthesis (`src/services/llm.py`)**
   - Asynchronous `LLMService` enforcing strict excerpt-only synthesis with inline citation markers `[1]`, `[2]`.
   - Emits canonical refusal `"I do not have enough information in the provided documents to answer this question."` for unsupported queries.

3. **RAG Schemas & Provenance Offsets (`src/schemas/rag.py`, `src/api/v1/endpoints/rag.py`)**
   - Returns grounded answer alongside structured citations recording `chunk_id`, `document_id`, `filename`, `start_offset`, and `end_offset`.

---

### Weeks 1 & 2 — Ingestion, Storage & Async Foundations (Completed)

1. **Storage & Extraction Pipeline (`src/services/storage.py`, `src/services/extractor.py`)**
   - LocalStorageService enforcing 10MB limit and computing hexadecimal SHA-256 digests.
   - Extractors supporting PDF, markdown, plain text, and Python files.

2. **Sliding-Window Chunking (`src/services/chunker.py`)**
   - Standardized configuration: `CHUNK_SIZE = 512`, `CHUNK_OVERLAP = 64`.
   - Preserves semantic continuity across window boundaries.

3. **Background Job Orchestration (`src/api/v1/endpoints/documents.py`, `src/models/processing_job.py`)**
   - Non-blocking document ingestion via FastAPI `BackgroundTasks`.
   - Independent database session allocation via `async_session_factory` preventing session leaks.
   - ProcessingJob lifecycle tracking: `PENDING` -> `IN_PROGRESS` -> `COMPLETED`.

---

## Current Test Suite Status

```
tests/test_agent.py ................................. [ 6 tests] -> PASSED
tests/test_auth.py .................................. [ 3 tests] -> PASSED
tests/test_documents.py ............................. [ 4 tests] -> PASSED
tests/test_health.py ................................ [ 2 tests] -> PASSED
tests/test_ingestion.py ............................. [ 7 tests] -> PASSED
tests/test_jobs.py .................................. [ 3 tests] -> PASSED
tests/test_projects.py .............................. [ 6 tests] -> PASSED
tests/test_rag.py ................................... [11 tests] -> PASSED
tests/test_retrieval.py ............................. [ 7 tests] -> PASSED
tests/test_search.py ................................ [ 5 tests] -> PASSED

Total: 54 passed in 22.10s (100% green)
```
