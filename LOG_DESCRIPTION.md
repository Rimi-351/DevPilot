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
> *"In Week 3, I engineered the document retrieval and semantic search pipeline for DevPilot. I modeled persistent DocumentChunks with JSON vector representations and Alembic migrations. In the background ingestion pipeline, text chunks are asynchronously vectorized using fastembed (bge-small-en-v1.5) and persisted with character offsets. I then implemented a multi-tenant semantic search endpoint computing cosine similarity### 🔹 Week 4: Grounded RAG, Citations & AI Evaluation

```

User Query ──► Keyword OR Vector Retrieval ──► Provenance Context Window ──► Grounded LLM Synthesis
                   (lexical overlap)              ([1], [2] Excerpts)           (Zero Extrapolation)
                OR (cosine similarity)                    │                           │
                                                  (No Evidence Found)        Citations & Claims
                                                          ▼                   (Verified Provenance)
                                         "I do not have enough information..."
```

#### 1. What Was Built
* **LLM & RAG Configuration:** Integrated configurable LLM provider settings (`LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`) into `Settings` with async `httpx` client support.
* **Grounded LLM Service (`src/services/llm.py`):** Asynchronous `LLMService` implementing `generate_grounded_answer` with strict system prompt grounding, citation extraction (`[1]`, `[2]`), and deterministic offline mock simulation for test isolation and zero API costs.
* **RAG Endpoint & Pydantic v2 Schemas (`src/schemas/rag.py` & `src/api/v1/endpoints/rag.py`):**
  - Schemas: `RagQueryRequest` (top_k, temperature constraints), `Citation` (citation_id, chunk_id, document_id, filename, start_offset, end_offset), and `RagResponse`.
  - Endpoint `POST /api/v1/projects/{project_id}/rag`: Validates project existence, executes multi-tenant semantic retrieval, numbers context excerpts, generates grounded synthesis, maps citation markers to exact chunk provenance.
* **Keyword Retrieval Baseline (`src/services/search.py`):**
  - `lexical_keyword_search(query, chunks)` — tokenizes query and chunk content, scores by intersection token count, returns chunks sorted by descending overlap.
  - Serves as a lightweight BM25-like baseline for benchmarking and hybrid search preparation.
* **IR Evaluation & Retrieval Benchmarking (`src/evaluation/`):**
  - `src/evaluation/benchmark.py` implementing `Recall@k` (k=1, 3, 5), Reciprocal Rank (RR), and Mean Reciprocal Rank (MRR).
  - `DEFAULT_BENCHMARK_DATASET` with 8 items: 5 standard domain-specific pairs + 3 explicit failure scenarios (`lexical_gap`, `boundary_split`, `unanswerable`).
  - `BenchmarkRunner.compare_retrieval_modes()` running both `keyword` and `vector` retrievers and returning side-by-side `BenchmarkResult` objects.
* **Background Task Race Condition Fix:** Identified that `async_session_factory` in `process_document_background` was using the production engine in tests. Fixed `tests/conftest.py` to monkey-patch both `src.core.database.async_session_factory` and `src.api.v1.endpoints.documents.async_session_factory` with the test session factory, achieving 37/37 tests passing.
* **Integration & Evaluation Test Suite (`tests/test_rag.py`):** 10 tests covering E2E grounded RAG, negative queries, multi-tenant isolation, benchmark metric calculations, keyword vs. vector mode comparison, and input validation boundaries.

#### 2. Keyword vs. Vector Retrieval Trade-offs

| Dimension            | Keyword (Lexical)                         | Semantic Vector                            |
|:---------------------|:------------------------------------------|:-------------------------------------------|
| **Mechanism**        | Token intersection scoring (TF overlap)   | 384-dim cosine similarity (BGE embeddings) |
| **Recall@1**         | 0.625                                     | 0.875                                      |
| **Recall@3**         | 0.750                                     | 1.000                                      |
| **MRR**              | 0.698                                     | 0.917                                      |
| **Strength**         | Exact identifiers, error codes, constants | Paraphrase, concept, intent queries        |
| **Weakness**         | Vocabulary mismatch / synonym gaps        | Exact string / rare token retrieval        |
| **Week 5 Plan**      | Hybrid BM25 + Dense with RRF              | Cross-encoder reranking pass               |

**Empirical Benchmark Takeaway:** Vector retrieval outperforms keyword across all aggregate metrics. However, keyword retrieval achieves Recall@1 = 1.0 on `lexical_gap` queries (exact code constant lookup), while vector retrieval achieves only 0.5, confirming the need for hybrid search in Week 5.

#### 3. Live E2E Swagger UI Verification Notes

**Test 1 — Grounded Positive Query:**
- Uploaded `company_policy.txt` (162 bytes) to a project via `POST /api/v1/documents/upload`.
- Job transitioned `PENDING → IN_PROGRESS → COMPLETED`; 1 `DocumentChunk` persisted with 384-dim embedding.
- Queried `POST /api/v1/projects/{id}/rag` → `"chunks_evaluated": 1`, answer contained inline `[1]` citation with offsets `start_offset=0, end_offset=162`.
- Grounded answer correctly cited "24 hours" from document; zero hallucination.

**Test 2 — Multi-Tenant Isolation:**
- Project A (company_policy.txt) queried for Project B (tech_stack.txt) content → received canonical refusal: *"I do not have enough information in the provided documents to answer this question."*
- `citations: []` confirmed — zero cross-tenant chunk leakage across distinct project UUIDs.
- Isolation enforced via `WHERE project_id = :project_id` in all retrieval queries at ORM level.

#### 4. Architecture Trade-offs
* **Prompt-Constrained Grounding vs. Speculative Fine-Tuning:** System-prompt instruction grounding is model-agnostic, zero-cost to update, and avoids continuous model training, at the expense of prompt context overhead.
* **In-Memory Cosine Ranking vs. Vector DB:** Application-layer ranking ensures dialect portability across SQLite and PostgreSQL, with a clean upgrade path to pgvector or Qdrant.

#### 5. Documented Failure Modes
* **Lexical Gap:** Queries using exact code constants (e.g., `NEGATIVE_RESPONSE`) rank lower in vector search (Recall@1=0.5); mitigated in W5 by BM25 + Dense hybrid.
* **Boundary Cuts:** Answers spanning two consecutive chunks degrade both keyword and vector Recall@1 to 0.5; mitigated by increasing chunk overlap and sentence-boundary chunking.
* **Negative Constraints:** LLMs may attempt partial answers without strict negative guardrails; mitigated by enforcing canonical refusal string and cosine score thresholds.

#### 💡 Interview Cheat Sheet
> *"In Week 4, I implemented grounded Retrieval-Augmented Generation (RAG) and a dual-mode retrieval evaluation harness in DevPilot. I engineered an asynchronous LLM service supporting both OpenAI-compatible endpoints and deterministic offline mock generators. The RAG pipeline retrieves top-k project chunks via vector similarity, labels context excerpts as [1], [2], and instructs the model to answer solely using provided excerpts or politely refuse when evidence is lacking. I also built a keyword lexical baseline retriever for benchmarking, a BenchmarkRunner computing Recall@k and MRR across 8 dataset items including 3 explicit failure scenarios, and confirmed live E2E grounded generation and strict multi-tenant isolation via Swagger UI. All 37 integration tests pass with zero warnings."*

---

### 🔹 Week 5: Improve Retrieval Quality & Reproducible Benchmark

```
User Query
    │
    ├──► Dense Vector Search (FastEmbed BGE-small-en-v1.5) ──┐
    │                                                        ├──► Reciprocal Rank Fusion (RRF, k=60)
    └──► Sparse Lexical Search (Rank-BM25 with index cache) ─┘        │
                                                                      ▼
                                                        Top-N Fused Candidate Chunks
                                                                      │
                                                                      ▼
                                                        Cross-Encoder Reranker
                                                        (ms-marco-MiniLM-L-6-v2)
                                                                      │
                                                                      ▼
                                                        Top-K Grounded Excerpts
                                                                      │
                                                                      ▼
                                                        Grounded LLM Generation
```

#### 1. Key Accomplishments & Deliverables

- **Hybrid Search via Reciprocal Rank Fusion (`src/services/retrieval/hybrid.py`):**
  - Combined semantic dense vector cosine similarity with lexical sparse BM25 scoring (`rank-bm25`).
  - Implemented Reciprocal Rank Fusion:
    $$RRF\_Score(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + \text{rank}(d) + 1} \quad (k=60)$$
  - Unified candidate deduplication by chunk ID, preserving metadata and attaching computed `rrf_score`.

- **In-Memory BM25 Index Caching:**
  - Designed `_bm25_cache: dict[str, tuple[int, BM25Okapi, list[dict]]]` to eliminate tokenization and index reconstruction bottlenecks.
  - Generates deterministic cache keys based on `project_id` or corpus chunk identifier hashes.
  - Re-tokenization occurs only when the corpus length or chunks change, yielding sub-50ms retrieval latencies on repeat queries.

- **Cross-Encoder Reranker (`src/services/retrieval/reranker.py`):**
  - Integrated `cross-encoder/ms-marco-MiniLM-L-6-v2` via `sentence-transformers` for deep query-passage cross-attention scoring.
  - Implemented `RerankerService.rerank(query, candidates, top_k)` predicting joint relevance scores and attaching `rerank_score`.
  - Built-in lazy loading and heuristic fallback mechanism ensures resilient execution in offline or resource-constrained environments.

- **Unified Multi-Mode Retrieval Pipeline (`src/services/retrieval/pipeline.py`):**
  - Created `retrieve_chunks()` supporting three retrieval paradigms:
    1. `"vector_only"`: Fast dense embedding search.
    2. `"hybrid"`: Dense + BM25 sparse search merged via RRF.
    3. `"hybrid_rerank"`: Dense + BM25 (RRF candidates) followed by Cross-Encoder reranking.
  - Integrated into `POST /api/v1/projects/{project_id}/rag` and `POST /api/v1/projects/{project_id}/search` with schema validation (`search_mode`, `chunk_limit`, `top_k`).

- **Reproducible Benchmark Runner (`src/evaluation/runner.py`):**
  - CLI benchmark runner (`python -m src.evaluation.runner`) evaluating:
    - **Hit@k**: Binary relevance success rate for ground-truth chunks in retrieved results.
    - **MRR (Mean Reciprocal Rank)**: Reciprocal rank of first matching ground-truth chunk.
    - **Latency Percentiles**: P50 and P95 latency measurements for retrieval and generation stages.
    - **Unsupported Claims Rate**: Lexical verification detecting answer tokens unsupported by retrieved context.
  - Added CLI flag aliases: `--dataset` (alias for `--data-path`), `--chunk-size` (default 512), and `--enable-reranker` (runs in `hybrid_rerank` mode).
  - Maintained benchmark datasets (`benchmarks/eval_data.jsonl`, `benchmarks/gold_standard.jsonl`) and persisted run artifacts to `artifacts/benchmark_results.json`.

- **Comprehensive Test Suite:**
  - 44 tests pass cleanly (37 integration/system tests + 7 dedicated retrieval/benchmark tests in `tests/test_retrieval.py` testing BM25 ranking, RRF scoring, reranker ordering, pipeline modes, and BM25 index caching).

#### 2. Benchmark Evaluation Summary

| Retrieval Mode | Hit@k (k=3) | MRR | P50 Ret (ms) | P95 Ret (ms) | P50 Gen (ms) | P95 Gen (ms) | Unsupported Claims |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Vector Only** | 1.00 | 1.00 | 50.46 | 1600.63 | 1152.25 | 1322.19 | 31.42% |
| **Hybrid (RRF)** | 1.00 | 1.00 | 47.74 | 66.07 | 1103.06 | 1279.50 | 31.42% |
| **Hybrid + Rerank** | 1.00 | 1.00 | 170.71 | 17157.27 | 957.38 | 1213.85 | 29.24% |

#### 💡 Interview Cheat Sheet
> *"In Week 5, I evolved DevPilot's retrieval architecture from basic bi-encoder vector search to an advanced two-stage hybrid retrieval and reranking pipeline. I implemented BM25 sparse search using rank-bm25 combined with dense semantic embeddings via Reciprocal Rank Fusion (RRF, k=60). To prevent redundant re-indexing on every query, I engineered an in-memory BM25 index cache with deterministic cache keys based on project IDs and chunk hashes. For second-stage scoring, I integrated a cross-encoder (ms-marco-MiniLM-L-6-v2) that evaluates joint query-passage attention, backed by a lazy loader and resilient heuristic fallback. I also built a reproducible CLI evaluation runner measuring Hit@k, MRR, P50/P95 latencies, and unsupported claims rates, persisting benchmark results to JSON. The entire 44-test suite passes with 100% green status."*

---

### 🔹 Week 5 Remediation: Multi-Tenant Security Hardening, 50-Query Benchmark & Containerized CI

```
                             ┌──────────────────────────────────┐
                             │       Incoming HTTP Request      │
                             └────────────────┬─────────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
             No / Empty X-API-Key                            Valid X-API-Key
                      │                                               │
                      ▼                                               ▼
             HTTP 401 Unauthorized                         Project Tenant Check
                                                     (project.tenant_id == api_key)
                                                                      │
                                              ┌───────────────────────┴───────────────────────┐
                                              ▼                                               ▼
                                      Tenant Mismatch                                    Tenant Match
                                              │                                               │
                                              ▼                                               ▼
                                     HTTP 403 Forbidden                             Authorized Execution
                                                                                  (CRUD, Search, RAG)
```

#### 1. What Was Built
* **50-Query Gold Standard Benchmark Dataset (`benchmarks/gold_standard_50.jsonl`):**
  - Expanded benchmark coverage to 50 realistic technical queries across 4 categories:
    1. 15 Exact keyword & identifier queries (`CHUNK_SIZE`, `X-API-Key`, `reciprocal_rank_fusion`, `BM25Okapi`).
    2. 15 Paraphrased & conceptual queries (multi-tenant isolation, sliding-window chunking, cross-encoder attention).
    3. 10 Multi-chunk fact synthesis queries across distinct documents and pipeline layers.
    4. 10 Out-of-scope negative constraint queries verifying canonical polite refusal (`NEGATIVE_RESPONSE`).
* **Evaluation Runner Parameter Sweeps (`src/evaluation/runner.py`):**
  - Automated grid sweep across chunk sizes (`chunk_size=512`) and top-$k \in [3, 5]$ for all three retrieval modes (`vector_only`, `hybrid`, `hybrid_rerank`).
  - Formalized `unsupported_claims_rate` metric measuring sentence-to-chunk token overlap ratio with a 0.40 threshold.
  - Persisted reproducible evaluation artifacts to `artifacts/benchmark_results.json`.
* **Multi-Tenant Security Hardening (`src/core/security.py`, `src/models/project.py`, `src/schemas/project.py`):**
  - `get_current_api_key` dependency parsing `X-API-Key` headers; returns `HTTP 401 Unauthorized` with `WWW-Authenticate: X-API-Key` on missing or whitespace keys.
  - Added `tenant_id` and `owner_api_key` columns to `Project` model with indexing and auto-assignment upon project creation.
  - Implemented `verify_project_tenant_access(project, current_api_key)` enforcing tenant ownership; raises `HTTP 403 Forbidden` on cross-tenant access.
  - Guarded all endpoints across projects, documents, background jobs, semantic search, and RAG.
  - Automated security tests in `tests/test_auth.py` verifying 401, 403, and authorized tenant lifecycles.
* **Production Multi-Stage Docker Container (`Dockerfile`, `docker-compose.yml`):**
  - Multi-stage build on `python:3.11-slim` with dedicated non-root user `devpilot` (UID 1000) and healthcheck on port 8000.
  - `docker-compose.yml` orchestrating API container with PostgreSQL 16 Alpine and persistent volumes (`storage_data`, `artifacts_data`, `postgres_data`).
* **Continuous Integration Pipeline (`.github/workflows/ci.yml`):**
  - GitHub Actions CI workflow executing `ruff check src/ tests/ --select E9,F63,F7,F82`, full test suite (`pytest -v`), and CLI benchmark runner verification.
* **Test Suite Expansion:** Total test count elevated to 48/48 tests passing (100% green).

#### 💡 Interview Cheat Sheet
> *"In the Week 5 Remediation milestone, I hardened DevPilot for enterprise multi-tenancy and production deployments. I introduced X-API-Key header authentication with strict 401 unauthenticated and 403 cross-tenant isolation across all project, document, search, and RAG endpoints. I scaled our evaluation dataset to a 50-query gold standard covering exact code identifiers, conceptual paraphrases, multi-chunk syntheses, and unanswerable negative queries, validating that our Cross-Encoder reranker maintains a perfect 1.00 MRR. Finally, I authored a multi-stage Dockerfile running under an unprivileged user, docker-compose orchestration with PostgreSQL 16, and a GitHub Actions CI pipeline running lint, test, and benchmark suites on every commit."*

---

### 🔹 Week 6: Bounded Agentic Workflows with Tool Calling & Structured Outputs

```
                                      BOUNDED FINITE STATE MACHINE (FSM)
  ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                                        │
  │    [Phase 1: SEARCH]     ──►    [Phase 2: INSPECT]     ──►   [Phase 3: SUMMARIZE]  ──►   [Phase 4: PROPOSE]   │
  │     (search_project)              (inspect_chunk)              (summarize_text)        (AgentProposal) │
  │                                                                                                        │
  └──────────────────┬─────────────────────────────┬────────────────────────────┬──────────────────────────┘
                     │                             │                            │
  ┌──────────────────▼─────────────────────────────▼────────────────────────────▼──────────────────────────┐
  │                                  GUARDED TOOL DISPATCHER FIREWALL                                      │
  │  1. Phase Boundary Gate: Blocks out-of-order calls (PHASE_VIOLATION)                                   │
  │  2. Ingress Validation: Strict Pydantic v2 schemas (VALIDATION_ERROR -> Reflected into Context)        │
  │  3. Timeout Isolation: Per-tool asyncio.wait_for wrapper (TIMEOUT after 3.0s, No Starvation)            │
  │  4. Fault Boundary: Exception fallback blocks return structured error payloads (EXECUTION_ERROR)       │
  │  5. Hard Loop Cap: Strict termination at MAX_ITERATIONS = 5 (MAX_ITERATIONS_REACHED)                  │
  └────────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
                                       Structured WorkflowReport
                               (Audit Trail Logs + Typed AgentProposal)
```

#### 1. What Was Built
* **Agent Service Schemas (`src/services/agent/schemas.py`):**
  - `WorkflowPhase(str, Enum)`: `SEARCH`, `INSPECT`, `SUMMARIZE`, `PROPOSE`.
  - Pydantic v2 tool input schemas with strict runtime validation:
    - `SearchInput`: `query: str` (min 3 chars).
    - `InspectInput`: `chunk_id: str` (UUID or hex chunk ID validation).
    - `SummarizeInput`: `text: str` (min 20 chars).
  - Telemetry and status enums: `ToolExecutionStatus` (`SUCCESS`, `VALIDATION_ERROR`, `TIMEOUT`, `EXECUTION_ERROR`, `PHASE_VIOLATION`), `ToolExecutionLog`.
  - Structured output schemas: `AgentProposal` (title, executive summary, action items, confidence score 0.0–1.0) and `WorkflowReport` (status, total iterations, total runtime, phase history, execution logs, final proposal).
* **Real Data-Bound Agent Tools (`src/services/agent/tools.py`):**
  - `search_project(query: str, project_id: UUID, session: AsyncSession)`: Executes Week 5 hybrid retrieval pipeline (`retrieve_chunks(search_mode="hybrid", top_k=5)`) scoped to target project.
  - `inspect_chunk(chunk_id: str, project_id: UUID, session: AsyncSession)`: Direct lookup of full text and metadata from `DocumentChunk` with project tenant boundaries.
  - `summarize_text(text: str)`: Calls `LLMService` to distill key findings into concise summaries, with resilient extractive fallback when LLM is unavailable.
* **Guarded Tool Dispatcher & Bounded Agent (`src/services/agent/workflow.py`):**
  - `GuardedToolDispatcher`: Pure-async 4-layer runtime firewall:
    1. Phase boundary checking (`PHASE_VIOLATION`).
    2. Pydantic v2 argument validation (`VALIDATION_ERROR`).
    3. `asyncio.wait_for` timeout isolation (`TIMEOUT`, default 3.0s).
    4. Fallback exception catching returning structured diagnostic error dictionaries into LLM context (`EXECUTION_ERROR`).
  - `BoundedAgent`:
    - Strict 4-phase finite state machine: `SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`.
    - Hard loop cap `MAX_ITERATIONS = 5`.
    - Contextual self-correction: failed tool calls reflect error details into context for prompt self-repair without crashing.
    - Synthesizes and returns validated `WorkflowReport`.
* **Authenticated Agent Workflow API Endpoint (`src/api/v1/endpoints/agent.py`):**
  - Route: `POST /api/v1/projects/{project_id}/agent/workflow` mounted under `/projects` with tag `["agent"]`.
  - Request Body: `AgentWorkflowRequest(goal: str)` (min 5, max 1000 characters).
  - Response: `WorkflowReport`.
  - Security: `X-API-Key` authentication (401), project existence check (404), tenant isolation via `verify_project_tenant_access` (403).
* **Comprehensive Test Suite (`tests/test_agent.py`):**
  - 6 unit & integration tests covering bounded phase progression, validation error reflection & self-correction, phase boundary protection, timeout isolation, loop cap termination, and authenticated API endpoint security.
  - Total project tests elevated to **54/54 passing** (100% green).

#### 2. Architecture Trade-offs
* **Bounded FSM vs. Autonomous ReAct Agent:** Free-form autonomous agents frequently suffer from infinite loops, hallucinated tool calls, and runaway cloud costs. A strictly bounded 4-phase state machine with hard iteration caps guarantees deterministic convergence, bounded token consumption, and predictable latency.
* **In-Context Error Reflection vs. Exception Raising:** Crashing the workflow upon invalid tool arguments or network timeouts causes severe UX degradation. Feeding structured error payloads back into the LLM context empowers the agent to autonomously correct its query or chunk identifier on subsequent iterations within its allocated iteration budget.

#### 💡 Interview Cheat Sheet
> *"In Week 6, I designed and implemented a production-grade Bounded Agentic Workflow for DevPilot. The agent is governed by a strict four-phase finite state machine (SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE) and bounded by a hard loop cap of 5 iterations. Tool execution is firewalled by a GuardedToolDispatcher that enforces phase boundaries, validates arguments at runtime using Pydantic v2, isolates each tool call with asyncio.wait_for timeouts (3.0s default), and captures exceptions to reflect structured error diagnostics back into the LLM context for in-flight self-correction. The tools connect directly to our Week 5 hybrid retrieval pipeline and PostgreSQL/SQLite ORM layer. I exposed the workflow via an authenticated endpoint (POST /api/v1/projects/{id}/agent/workflow) with strict multi-tenant isolation, supported by comprehensive pytest coverage bringing our test suite to 54/54 passing."*


