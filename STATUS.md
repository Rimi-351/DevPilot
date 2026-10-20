# DevPilot Project Status

**Current Target:** Week 9 — Backend Hardening, Object-Level Authorization, and Error Boundary Testing  
**Status:** **Week 9 COMPLETE** — Enterprise Backend Hardening, Object-Level Authorization, Resilient Ingestion State Machines, Composite Indexes, Bounded Pagination & Anti-Hallucination Guardrails  
**Last Verified:** `pytest -v` → **83/83 integration tests passing, 0 warnings**  
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
| **Week 7** | Multilingual Evaluation Benchmark & System Rigor (100 Queries) | ✅ Complete | 4 tests |
| **Week 8** | Make Retrieval Your Differentiator (Head-to-Head Evaluation & Production Champion) | ✅ Complete | 3 tests |
| **Week 9** | Backend Hardening, Object-Level Auth, State Machines, Bounded Pagination & Anti-Hallucination Guardrails | ✅ Complete | 22 tests (`test_boundaries.py`, `test_jobs.py`, `test_ingestion.py`, `test_rag.py`) |
| **Total** | **Comprehensive Full-Stack AI Platform** | **100% Green** | **83/83 Passing** |

---

## Completed Architecture Deliverables

### Week 9 — Backend Hardening, Object-Level Authorization & Anti-Hallucination Guardrails (COMPLETED)

1. **Object-Level Authorization Matrix (`src/core/security.py`, `src/api/v1/endpoints/`)**
   - Enforced 100% object-level multi-tenant isolation across all 6 API routers (`Projects`, `Documents`, `Search`, `RAG`, `Agent`, `Jobs`).
   - Hardened `/api/v1/jobs` endpoints to verify target `project_id` tenant ownership, returning `HTTP 403 Forbidden` on cross-tenant mutation and scoping unfiltered listings strictly to projects owned by the authenticated tenant.
2. **Resilient Background Ingestion State Machine (`src/services/ingestion/pipeline.py`, `src/models/processing_job.py`)**
   - Transitioned background ingestion into an explicit state machine: `PENDING` $\rightarrow$ `PROCESSING` (recording `started_at`) $\rightarrow$ `COMPLETED` (recording `completed_at` and chunk metadata).
   - Wrapped pipeline in transactional rollback barriers: on any extraction, chunking, or embedding error, dirty database state is rolled back (`await session.rollback()`) and the job cleanly transitions to `JobStatus.FAILED` with non-empty diagnostic `error_message`.
3. **Composite Database Indexes & Deterministic Bounded Pagination (`src/models/`, `alembic/versions/`, `src/schemas/common.py`)**
   - Declared and migrated 6 multi-tenant composite indexes: `(tenant_id, created_at)` on `projects`, `(project_id, created_at)` and `(project_id, filename)` on `documents`, `(document_id, chunk_index)` and `(project_id, document_id)` on `document_chunks`, and `(project_id, status, created_at)` on `processing_jobs`.
   - Bounded pagination parameters across list endpoints (`skip: int = Query(0, ge=0)`, `limit: int = Query(20, ge=1, le=100)`), rejecting malicious offsets with `HTTP 422`.
   - Enforced deterministic tie-breaking sorting (`ORDER BY created_at DESC, id ASC`) preventing page drift and item duplication.
4. **Citation Verification & Anti-Hallucination Guardrails (`src/core/guardrails.py`, `src/services/rag.py`)**
   - Implemented `CitationVerificationService` auditing all citation tags (`[1]`, `[1, 2]`, `[chunk: UUID]`, `[doc: UUID]`) against retrieved context chunks.
   - Automated post-processing strips out-of-bounds indices (e.g., `[99]`) and unretrieved UUID references from final answer text.
   - Computes and exposes grounding telemetry: `citation_correctness`, `unsupported_claims_rate`, `is_grounded`, and `invalid_citations_stripped`.
   - Guaranteed polite refusal without factual hallucination on negative queries (*"What is the secret recipe of Coca-Cola?"*).
5. **Chaos & Boundary Fault-Injection Test Suite (`tests/test_boundaries.py`)**
   - Validated system resilience against malformed ingress payloads, upstream LLM timeouts/503 errors, storage size and extension limits, and cross-tenant attacks.

### Week 8 — Make Retrieval Your Differentiator (COMPLETED)

1. **Error Analysis of Non-Latin Tokenization Explosion (`reports/WEEK_8_ERROR_ANALYSIS.md`)**
   - Isolated and diagnosed failure pattern where the monolingual English cross-encoder (`ms-marco-MiniLM-L-6-v2`) collapsed on native Bengali script (0.2788 MRR, 19 rank demotions) due to WordPiece 30k vocabulary fragmentation.
   - Bengali script words disintegrated into 4–6 character atoms and combining vowel diacritics (`কার`), scattering cross-attention matrices and biasing rankings towards irrelevant passages with spurious Latin loanwords.
2. **Script-Aware Dynamic Routing Dispatcher (Approach A, `src/services/retrieval/reranker.py`)**
   - Implemented Unicode script detection (`[\u0980-\u09ff]`) via `has_bengali_script()` with dynamic bypass guardrail (`reranker_engine = "script_aware_bypass"`).
   - Rescued native Bangla Recall@5 to 0.8485 (+75.0%) and eliminated all 19 rank demotions by routing directly to pristine Hybrid RRF rankings, maintaining an ultra-lean footprint of 148 ms P50 / 191 ms P95 at 86.7 MB RAM.
3. **Multilingual Cross-Encoder Integration (Approach B, `src/services/retrieval/reranker.py`)**
   - Integrated `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (12-layer XLM-RoBERTa backbone, 117.6M parameters) featuring a 250,000-token multilingual SentencePiece vocabulary.
   - Evaluated native Bengali morphemes whole (`_সিস্টেম`, `_ডেটাবেস`), rocketing native Bangla MRR to **0.9051 (+224.6%)** and Recall@5 to **0.9697**.
4. **Head-to-Head Empirical Benchmarking (`scripts/benchmark_head_to_head.py`, `reports/WEEK_8_OPTIMIZATION_RESULT.md`)**
   - Empirically evaluated 4 candidate architectures across a 100-query held-out gold benchmark (34 English, 33 Bangla, 33 Banglish):
     1. Baseline (Un-guarded Monolingual): 0.7015 Global MRR, 63.0% Rank #1
     2. Approach A (Script-Aware Bypass): 0.7630 Global MRR, 64.0% Rank #1
     3. Approach B (Multilingual CE `mmarco-L12`): 0.8675 Global MRR, 79.0% Rank #1
     4. Approach A+B Hybrid (Neural-Symbolic Consensus): **0.8748 Global MRR, 80.0% Rank #1 hits**
5. **Production Settings Wiring & RRF Blending (`src/core/config.py`, `src/services/retrieval/reranker.py`)**
   - Designated and configured **Approach A+B Hybrid** as the primary default in `Settings`:
     - `RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"`
     - `RERANKER_ENABLE_SCRIPT_BYPASS = False`
     - `RERANKER_BLEND_RRF_WEIGHT = 0.2`
   - Formulated neural-symbolic consensus blending $80\%$ cross-encoder neural sigmoid with $20\%$ normalized Hybrid RRF consensus, stabilizing cross-lingual calibration drifts on English (0.8284) and Banglish (0.9394).
   - Maintained full environment variable configurability for low-resource Edge deployments (Approach A).

### Week 7 — Multilingual Benchmark & System Rigor (Completed)

1. **Multilingual Unicode Tokenizer & BM25 Support (`src/services/retrieval/hybrid.py`)**
   - Implemented `[\w\u0980-\u09ff\u200c\u200d]+` tokenization supporting Bengali script, combining vowel marks, ZWJ/ZWNJ, and Romanized Banglish.
2. **Multilingual Embedding Service (`src/services/embedding.py`)**
   - Configured `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` with FastEmbed fallback.
3. **100-Query Multilingual Gold Standard Benchmark (`benchmarks/multilingual_gold_100.jsonl`)**
   - Curated balanced dataset: 34 English technical queries, 33 pure Bengali script queries, 33 Romanized Banglish queries.
4. **Language-Sliced Evaluation Runner (`src/evaluation/runner.py`)**
   - Added `--lang {all,english,bangla,banglish}` and `--sweep` CLI support computing Recall@5, MRR, P50/P95 latencies, and unsupported claims rate per slice.


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
tests/test_boundaries.py ............................ [ 9 tests] -> PASSED
tests/test_documents.py ............................. [ 4 tests] -> PASSED
tests/test_health.py ................................ [ 2 tests] -> PASSED
tests/test_ingestion.py ............................. [10 tests] -> PASSED
tests/test_jobs.py .................................. [ 7 tests] -> PASSED
tests/test_projects.py .............................. [ 6 tests] -> PASSED
tests/test_rag.py ................................... [16 tests] -> PASSED
tests/test_retrieval.py ............................. [15 tests] -> PASSED
tests/test_search.py ................................ [ 5 tests] -> PASSED

Total: 83 passed (100% green)
```

---

## Next Milestone Preview — Week 10: Production Observability, Distributed Rate Limiting & Streaming Telemetry

With retrieval differentiation, object-level multi-tenant authorization, background state reporting, composite database indexes, and citation anti-hallucination guardrails fully verified (**83/83 passing tests**), Week 10 prepares DevPilot for enterprise production scaling and operational visibility:

### Planned Engineering Objectives

1. **Distributed Tenant-Scoped Rate Limiting & Concurrency Controls (`src/core/limiter.py`)**
   - Implement tenant-level token bucket and sliding-window rate limiters across Search, RAG, and Agent dispatching to eliminate "noisy neighbor" resource starvation.
   - Guard CPU-intensive background tasks (chunking, embedding generation, reranking) with concurrency-bounded `asyncio.Semaphore` queues.

2. **Real-Time Streaming Telemetry & SSE Endpoints (`src/api/v1/endpoints/rag.py`, `src/services/streaming.py`)**
   - Provide Server-Sent Events (SSE) streaming for RAG generation and multi-step agent workflows.
   - Stream verified citation tags and incremental token deltas directly to frontend clients with low initial latency (TTFT < 300ms).

3. **OpenTelemetry & Prometheus Metrics Export (`src/core/telemetry.py`)**
   - Standardize structured JSON audit logging across all API endpoints with mandatory `X-Request-ID` correlation headers.
   - Expose Prometheus `/metrics` endpoint instrumenting request rates, P50/P95 latencies, subword token expansions, cache hit ratios, and memory footprints.

4. **Production Deployment & Helm / Kubernetes Blueprints (`deploy/`)**
   - Author production Kubernetes Helm charts, Horizontal Pod Autoscaling (HPA) policies based on GPU/CPU utilization, and health check readiness/liveness probes.
