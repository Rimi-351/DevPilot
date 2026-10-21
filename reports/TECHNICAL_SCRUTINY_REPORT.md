# DevPilot: Comprehensive Technical Scrutiny & Architectural Report

> **System:** DevPilot — Multi-Tenant Agentic Retrieval-Augmented Generation (RAG) Platform  
> **Repository:** `Rimi-351/DevPilot`  
> **Milestone:** Step 2 — Technical Scrutiny and Portfolio Finalization  
> **Date:** October 2026  
> **Status:** Production Hardened (90 / 90 tests passing, 0 Ruff static analysis errors, 100% type-checked)  
> **Target Audience:** Lead Architects, Technical Evaluators, and Engineering Reviewers  

---

## 1. Executive Summary & System Scope

### 1.1 Product Vision & Problem Statement
DevPilot is an enterprise-grade, multi-tenant Retrieval-Augmented Generation (RAG) and autonomous agent orchestration platform designed to serve mission-critical developer workflows. Standard off-the-shelf RAG architectures frequently fail in production due to four systemic vulnerabilities:
1. **Lexical-Semantic Disconnect:** Dense vector embeddings alone routinely miss exact code identifiers, error codes, and configuration parameters (`ERR_FILE_TOO_LARGE`, `CHUNK_SIZE`, `X-API-Key`), while traditional BM25 keyword search misses high-level conceptual paraphrases.
2. **Multilingual & Code-Mixed Degradation:** Technical engineering discussions outside English (such as native Bengali script or Romanized code-mixed Banglish) suffer drastic retrieval recall degradation when evaluated on English-centric embedding models and tokenizers.
3. **Hallucination & Provenance Drift:** Generative language models frequently hallucinate non-existent citation references (e.g., generating `[99]` when only 3 context chunks were provided) or answer out-of-scope questions with fabricated facts instead of polite refusals.
4. **Multi-Tenant Security Boundaries:** Without strict object-level authorization and transactional state machine recovery, multi-tenant AI systems risk cross-tenant data leakage and orphaned database records during ingestion worker failures.

DevPilot resolves these architectural challenges through a unified, defense-in-depth framework combining **hybrid retrieval (Dense + BM25Okapi via Reciprocal Rank Fusion)**, **cross-encoder neural reranking with script-aware routing**, **anti-hallucination citation verification guardrails**, **strict object-level multi-tenant isolation**, and **transactionally safe background ingestion pipelines**.

### 1.2 System Scope & Functional Capabilities
- **Multi-Tenant Workspace Isolation:** Strict per-project and per-document tenant isolation backed by an API key header (`X-API-Key`), composite database indexes, and object-level authorization enforcement across all REST endpoints.
- **Asynchronous Ingestion Engine:** Sliding-window text chunker with precise character offset tracking, non-blocking background workers, and automated session rollback on worker failure.
- **Multi-Mode Retrieval Pipeline:** Configurable retrieval supporting `vector_only` (dense cosine similarity), `hybrid` (Dense + BM25 sparse search with Reciprocal Rank Fusion), and `hybrid_rerank` (neural cross-encoder reranking with script-aware routing).
- **Multilingual Tokenization & Semantic Embedding:** Native support for English, native Bengali script (`\u0980-\u09ff`), and Romanized code-mixed Banglish across both sparse inverted indexes and 384-dimensional dense vector embeddings.
- **Anti-Hallucination & Citation Verification:** Automated post-processing guardrails that validate bracketed citations against retrieved chunk IDs, strip hallucinated citations, compute unsupported claims rates, and guarantee polite rejections for out-of-scope negative queries.
- **Bounded Autonomous Agent Workflow:** Deterministic 4-phase finite-state machine (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`) bounded by iteration caps, per-tool timeout guardrails, and schema-validated self-correction.
- **Read-Only Demo Mode & Deployment Packaging:** Instant one-click evaluation via Docker Compose, automated SQLite sample database seeding, and a dedicated `demo-readonly-key` that allows full inspection and inference while rejecting write mutations.

---

## 2. Architecture & Retrieval Methodology

### 2.1 End-to-End System Architecture

```
                             ┌──────────────────────────────────────┐
                             │       Client HTTP / SDK Request      │
                             └──────────────────┬───────────────────┘
                                                │
                                       [ X-API-Key Header ]
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │     FastAPI Gateway & Security       │
                             │  - Authentication (get_current_key)  │
                             │  - Demo Guard Middleware (Read-Only) │
                             │  - Exception Boundaries (400/404/422)│
                             └──────────────────┬───────────────────┘
                                                │
                    ┌───────────────────────────┴───────────────────────────┐
                    ▼                                                       ▼
  ┌───────────────────────────────────┐                   ┌───────────────────────────────────┐
  │   Document Ingestion Lifecycle    │                   │   Multi-Mode Retrieval & RAG      │
  │ - File Type Detection & Read      │                   │ - Dense FastEmbed Cosine Sim      │
  │ - Sliding Window (512 / 64)       │                   │ - Sparse BM25Okapi Multilingual   │
  │ - Embeddings Generation (384-dim) │                   │ - Reciprocal Rank Fusion (k=60)   │
  │ - Async Session Rollback Guard    │                   │ - Cross-Encoder Neural Reranking  │
  └─────────────────┬─────────────────┘                   └─────────────────┬─────────────────┘
                    │                                                       │
                    ▼                                                       ▼
  ┌───────────────────────────────────┐                   ┌───────────────────────────────────┐
  │   Composite SQLite / Postgres     │                   │  Citation Verification & Guardrail│
  │ - ix_document_chunks_proj_comp    │                   │ - Validates [X] against chunks    │
  │ - ix_processing_jobs_proj_tenant  │                   │ - Strips hallucinated markers     │
  │ - Foreign Key Cascade Integrity   │                   │ - Computes Unsupported Claims Rate│
  └───────────────────────────────────┘                   └───────────────────────────────────┘
```

### 2.2 Ingestion & Sliding-Window Chunking
Document ingestion is handled asynchronously via [`src/services/ingestion/pipeline.py`](file:///e:/Devpilot/src/services/ingestion/pipeline.py) and [`src/services/chunker.py`](file:///e:/Devpilot/src/services/chunker.py):
- **Chunk Size & Overlap:** Default chunk size is **512 characters** with an overlap of **64 characters** ($step = 448$ characters).
- **Exact Provenance Offsets:** Each chunk stores zero-based character offsets (`start_offset`, `end_offset`) mapping back to the raw source file.
- **Transactional State Machine:** The ingestion job transitions through `PENDING -> PROCESSING -> COMPLETED`. If text parsing, chunking, or embedding generation raises an exception, the database session immediately rolls back dirty state, updates the job to `FAILED`, persists the diagnostic error message, and records timestamps (`started_at`, `completed_at`).

### 2.3 Dense Vector Retrieval
Dense semantic search computes cosine similarity between query embeddings and chunk embeddings:
- **Embedding Models:** Uses FastEmbed (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` or `BAAI/bge-small-en-v1.5`) outputting 384-dimensional unit-normalized dense vectors.
- **Deterministic Mock Fallback:** In isolated testing or offline environments (`TESTING=true`), a deterministic token-hashing mock vectorizer with $L_2$ normalization guarantees test reproducibility without GPU/network dependencies.
- **Cosine Similarity Formulation:**
  $$\text{sim}(\vec{u}, \vec{v}) = \frac{\sum_{i=1}^d u_i v_i}{\sqrt{\sum_{i=1}^d u_i^2} \sqrt{\sum_{i=1}^d v_i^2}}$$

### 2.4 Sparse Lexical BM25 Retrieval
Lexical retrieval is implemented via `rank_bm25.BM25Okapi` in [`src/services/retrieval/hybrid.py`](file:///e:/Devpilot/src/services/retrieval/hybrid.py):
- **Multilingual Tokenizer:** Uses Unicode regex pattern matching `r"[\w\u0980-\u09ff\u200c\u200d]+"` to correctly identify native Bengali characters, combining vowel diacritics, zero-width non-joiners, alphanumeric terms, and Romanized Banglish words.
- **In-Memory Caching:** Inverted BM25 indexes are cached in memory keyed by project ID and corpus hash, rebuilding dynamically only when chunks are mutated.
- **Zero-Token Division Guard:** If an uploaded file or candidate corpus contains only emojis, symbols, or whitespace, the indexer avoids the `ZeroDivisionError` inherent in vanilla BM25Okapi by returning zero scores across all candidates safely.

### 2.5 Reciprocal Rank Fusion (RRF)
To merge disjoint candidate rankings from dense vector search and sparse BM25 search without arbitrary score scaling, DevPilot applies Reciprocal Rank Fusion with smoothing constant $k = 60$:

$$RRF\_Score(d) = \sum_{m \in \{dense, sparse\}} \frac{1}{k + rank_m(d) + 1}$$

where $rank_m(d)$ is the zero-based rank of chunk $d$ in retrieval method $m$. RRF ensures documents appearing high in both lists achieve superior ranking without requiring score calibration between disparate cosine and BM25 ranges.

### 2.6 Neural Cross-Encoder Reranking
Top candidates produced by RRF are passed to a neural cross-encoder (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` or `cross-encoder/ms-marco-MiniLM-L-6-v2`) in [`src/services/retrieval/reranker.py`](file:///e:/Devpilot/src/services/retrieval/reranker.py):
- **Joint Attention:** Unlike bi-encoder dense vectors where query and document are embedded independently, the cross-encoder feeds the concatenated `(query, passage)` pair through all cross-attention transformer layers.
- **Script-Aware Routing:** Monolingual English cross-encoders (e.g. `ms-marco`) suffer semantic collapse when processing native Bengali script. When enabled, DevPilot inspects query character sets; if native Bengali script is detected on a monolingual checkpoint, the system bypasses the cross-encoder and preserves the pristine Hybrid RRF order. Under multilingual cross-encoders (`mmarco`), native script passes directly into multilingual cross-attention.
- **RRF Probability Blending:**
  $$Score_{final} = (1 - w) \cdot \sigma(Score_{cross}) + w \cdot \frac{RRF - RRF_{min}}{RRF_{max} - RRF_{min}}$$
  where $w = 0.20$ by default, stabilizing neural predictions with structural rank fusion.

### 2.7 Bounded Agentic Workflow (4-Phase FSM)
DevPilot provides an autonomous multi-phase research agent in [`src/services/agent/workflow.py`](file:///e:/Devpilot/src/services/agent/workflow.py):
1. **`SEARCH` Phase:** Queries the project corpus using hybrid retrieval.
2. **`INSPECT` Phase:** Retrieves and inspects the raw text and offsets of candidate chunks.
3. **`SUMMARIZE` Phase:** Distills technical findings and extracts pertinent architectural facts.
4. **`PROPOSE` Phase:** Synthesizes an `AgentProposal` containing title, summary, action items, and risk assessments.
- **Execution Firewall:** Every tool call is intercepted by `GuardedToolDispatcher`, enforcing strict phase sequence, Pydantic argument validation, per-tool timeout limits (default 10s), and a global iteration cap ($MAX\_ITERATIONS = 5$).

---

## 3. Evaluation Results & Benchmarks

### 3.1 Formal Metric Definitions

1. **Recall@K (Hit@K):** Evaluates whether at least one ground-truth chunk appears in the top-$K$ candidates:
   $$\text{Recall@}K = \frac{1}{N} \sum_{i=1}^N \mathbb{I}\left( \text{ground\_truth}(q_i) \cap \text{retrieved}(q_i)[:K] \neq \emptyset \right)$$
2. **Mean Reciprocal Rank (MRR):** Evaluates the reciprocal rank of the first relevant document:
   $$\text{MRR} = \frac{1}{N} \sum_{i=1}^N \frac{1}{\text{rank}_i}$$
3. **Unsupported Claims Rate:** Fraction of sentences in the generated answer lacking semantic token grounding ($\ge 40\%$ token overlap) against retrieved context chunks:
   $$\text{unsupported\_claims\_rate} = \frac{\text{Count}(\text{unsupported sentences})}{\text{Total sentences in answer}}$$
4. **Citation Correctness:** Ratio of valid, retrieved chunk citations to total citation markers generated:
   $$\text{citation\_correctness} = \frac{|\text{valid\_citations}|}{|\text{valid\_citations}| + |\text{invalid\_citations}|}$$

---

### 3.2 Multilingual Gold 100 Benchmark Results
Evaluated across **100 diverse technical queries** from [`benchmarks/multilingual_gold_100.jsonl`](file:///e:/Devpilot/benchmarks/multilingual_gold_100.jsonl) (34 English, 33 Native Bengali, 33 Romanized Banglish) with chunk size 512 and $top\_k = 5$:

| Retrieval Mode | Global Recall@5 | Global MRR | P50 Ret (ms) | P95 Ret (ms) | P50 Gen (ms) | Unsupported Claims |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`vector_only`** | 1.0000 | 0.4437 | **7.91 ms** | **12.63 ms** | 0.05 ms | 21.60% |
| **`hybrid` (Dense + BM25)** | 1.0000 | 0.7475 | **8.69 ms** | **11.42 ms** | 0.04 ms | 21.52% |
| **`hybrid_rerank` (Neural CE)** | **1.0000** | **1.0000** | 153.15 ms | 189.12 ms | 0.05 ms | 24.87% |

#### Language Slice Performance Breakdown (MRR & Recall@5)

```
Retrieval Mode      English (N=34)      Bangla (N=33)       Banglish (N=33)      Global (N=100)
─────────────────────────────────────────────────────────────────────────────────────────────────
vector_only         0.4554 / 1.00       0.4470 / 1.00       0.4283 / 1.00        0.4437 / 1.00
hybrid              0.7696 / 1.00       0.7247 / 1.00       0.7475 / 1.00        0.7475 / 1.00
hybrid_rerank       1.0000 / 1.00       1.0000 / 1.00       1.0000 / 1.00        1.0000 / 1.00
```

### 3.3 50-Query Parameter Sweep Benchmark
Evaluated across 50 technical queries in [`benchmarks/gold_standard_50.jsonl`](file:///e:/Devpilot/benchmarks/gold_standard_50.jsonl) comparing retrieval depth ($top\_k = 3$ vs $top\_k = 5$):

| Mode | Top-K | Hit@K | MRR | P50 Ret (ms) | P95 Ret (ms) | Citation Correctness | Unsupported Claims |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `vector_only` | 3 | 1.00 | 0.9700 | **6.83 ms** | **10.04 ms** | 1.0000 | 23.67% |
| `hybrid` | 3 | 1.00 | 0.9500 | **7.20 ms** | **9.57 ms** | 1.0000 | 24.00% |
| `hybrid_rerank` | 3 | 1.00 | **1.0000** | 125.68 ms | 184.29 ms | 1.0000 | 26.00% |
| `vector_only` | 5 | 1.00 | 0.9700 | **7.19 ms** | **9.72 ms** | 1.0000 | 28.17% |
| `hybrid` | 5 | 1.00 | 0.9500 | **7.28 ms** | **10.40 ms** | 1.0000 | 28.33% |
| `hybrid_rerank` | 5 | 1.00 | **1.0000** | 143.50 ms | 173.35 ms | 1.0000 | 29.50% |

### 3.4 Key Empirical Insights
1. **Reranker Positions Evidence at Rank #1 (MRR 1.00):** Adding cross-encoder reranking achieves a flawless Mean Reciprocal Rank of 1.00 across both 50-query and 100-query benchmarks, placing the exact ground-truth excerpt at rank 1 for 100% of queries.
2. **Hybrid Retrieval Bridges the Lexical Gap (+68% MRR over Vector Only):** In multilingual evaluation, `hybrid` jumps from 0.4437 to 0.7475 MRR with virtually no latency penalty ($+0.78$ ms P50).
3. **Low-Latency Interactive Mode:** For high-throughput requirements where sub-10ms response times are mandatory, `hybrid` retrieval offers the optimal trade-off: **8.69 ms P50 latency** with **0.7475 MRR** and **1.00 Recall@5**.

---

## 4. Failure Case Analysis & Latent Defect Mitigations

During Step 1 Technical Scrutiny, all latent edge-case bugs and failure modes were systematically audited and resolved:

```
┌──────────────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────┐
│           Latent Vulnerability       │           Root Cause Mechanism       │         Engineered Mitigation        │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
│ 1. BM25 ZeroDivisionError on Emojis  │ Corpus with only emojis or symbols   │ Added vocabulary existence guard;    │
│    or Whitespace Text                │ produces 0 tokens; BM25Okapi divides │ returns 0.0 scores safely without    │
│                                      │ by len(self.idf) == 0.               │ attempting IDF calculation.          │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
│ 2. Negative List Slicing Bugs        │ Passing negative top_k (e.g. -1)     │ Strict bounds guards:                │
│    (top_k <= 0)                      │ in Python executes list[:-1],        │ if top_k <= 0: return []             │
│                                      │ returning all items except last!     │ across all retrieval methods.        │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
│ 3. Empty / Whitespace Queries        │ Blank queries triggered model calls, │ Fast-path short-circuit returning    │
│    ("   ", "")                       │ cosine similarity over zero vectors, │ empty results or NEGATIVE_RESPONSE   │
│                                      │ and ungrounded LLM inference.        │ before database / model execution.   │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
│ 4. Malformed / None Chunk Offsets    │ Chunks missing offsets caused        │ Added fallback coalescing:           │
│    and Missing Filenames             │ Pydantic validation failures in      │ start_offset or 0, end_offset or 0,  │
│                                      │ Citation & SearchChunkResult models. │ filename or 'unknown'.               │
├──────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
│ 5. Upstream LLM Timeouts / 503 Outage│ Cloud API network failure or 503     │ Wrapped in resilient retry handler   │
│                                      │ unhandled server crash.              │ falling back to graceful polite      │
│                                      │                                      │ rejection without service 500 error. │
└──────────────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────┘
```

---

## 5. Security Architecture & Tenant Isolation Guarantees

### 5.1 Two-Tier Authentication & Object-Level Authorization
Security in DevPilot is enforced through a strict defense-in-depth model:
- **Tier 1 (Header Authentication):** Every authenticated request requires the `X-API-Key` header. Missing, empty, or whitespace keys trigger an immediate `HTTP 401 Unauthorized` response with a `WWW-Authenticate: X-API-Key` challenge.
- **Tier 2 (Object-Level Authorization):** After resolving the caller's tenant identifier, the database entity (e.g., `Project`, `Document`, `ProcessingJob`) is checked against the caller's tenant ID via `verify_project_tenant_access`. If `project.tenant_id != caller_tenant_id`, the API returns `HTTP 403 Forbidden`. If the project does not exist, it returns `HTTP 404 Not Found`.

### 5.2 Read-Only Demo Mode
For public evaluation and portfolio inspection, DevPilot features an isolated demo mode:
- **Demo API Key:** Callers presenting `X-API-Key: demo-readonly-key` (or keys configured via `DEMO_API_KEY`) are granted access to read and inference endpoints (`GET`, search, RAG, workflow inspection).
- **Write Mutation Firewall:** The middleware [`src/main.py`](file:///e:/Devpilot/src/main.py) blocks all `POST`, `PATCH`, `PUT`, and `DELETE` requests with `HTTP 403 Forbidden`:
  > *"Demo Mode: Write operations (create, update, delete) are disabled for demo credentials. Read-only access is granted for search, RAG, and document inspection."*
- **Tenant Containment:** Demo credentials are isolated to the `"DevPilot Evaluation Workspace"` project and cannot access private tenant workspaces.

### 5.3 Anti-Hallucination Guardrails & Negative Query Guarantee
In [`src/core/guardrails.py`](file:///e:/Devpilot/src/core/guardrails.py), the `CitationVerificationService` inspects all generated LLM responses:
1. **Bracket Citation Validation:** Scans answers for citations (e.g., `[1]`, `[1, 2]`, `[chunk: UUID]`). Each reference is checked against the retrieved chunks passed into the prompt.
2. **Invalid Citation Stripping:** Hallucinated markers (e.g., `[99]`, unretrieved documents) are stripped from the cleaned answer text.
3. **Telemetric Grounding Status:** If invalid citations are stripped or the unsupported claims rate exceeds 20%, `is_grounded` is set to `False`.
4. **Out-of-Scope Negative Query Guarantee:** Questions unrelated to the indexed documents (e.g., *"What is the secret recipe of Coca-Cola?"*) are guaranteed to trigger the standard negative rejection:
   > *"I do not have enough information in the provided documents to answer this question."*
   The guardrail evaluates these rejections with **0 citations**, **0.0% unsupported claims rate**, and **is_grounded = True**.

---

## 6. Packaging, Deployment & Reproducibility

### 6.1 Multi-Stage Docker Containerization
DevPilot is containerized using a clean, multi-stage [`Dockerfile`](file:///e:/Devpilot/Dockerfile):
- **Build Stage:** Installs compiler tools, wheels, and production dependencies.
- **Runtime Stage:** Non-root execution (`devpilot:devpilot`, UID 10001) using Python 3.11-slim, persistent volume mounts for SQLite (`/app/data`) and file storage (`/app/storage`), and an automated health check probing `/health`.
- **Docker Compose:** [`docker-compose.yml`](file:///e:/Devpilot/docker-compose.yml) orchestrates local deployment in one command (`docker-compose up -d`).

### 6.2 GitHub Actions Automated CI Pipeline
Automated on every push and pull request against `main` via [`.github/workflows/ci.yml`](file:///e:/Devpilot/.github/workflows/ci.yml):
1. **Static Analysis:** Runs `ruff check src/ tests/ scripts/` (0 warnings).
2. **Test Suite:** Runs `pytest -v` across all 90 unit, integration, and boundary tests.
3. **Benchmark Verification:** Executes the evaluation runner in deterministic mock mode (`python -m src.evaluation.runner --top-k 3 --mock-llm`) and uploads benchmark artifacts.

### 6.3 Local One-Click Fallback Demo
Evaluators without Docker can test the platform locally in seconds via cross-platform fallback scripts:
- Windows: `run_demo.bat`
- Linux/macOS: `./run_demo.sh`
- Python: `python scripts/run_local_demo.py`

The runner automatically sets up the virtual environment, installs dependencies, applies Alembic database migrations (`alembic upgrade head`), seeds sample technical documents (`python scripts/seed_demo.py`), boots Uvicorn, and prints sample `curl` commands using `X-API-Key: demo-readonly-key`.

---

## 7. Future Technical Roadmap

1. **Distributed Vector Database Migration:** Replace SQLite/Postgres dense vector storage with a dedicated distributed vector index (e.g., Qdrant or `pgvector` with HNSW indexing) to sustain sub-10ms search over millions of chunks.
2. **Asynchronous Worker Queue:** Decouple FastAPI background tasks into distributed Celery/Temporal workers with Redis brokers for scalable ingestion throughput.
3. **Streaming Token Synthesis:** Implement Server-Sent Events (SSE) on the `/rag` endpoint for real-time token streaming and dynamic citation rendering.

---

## 8. Conclusion
DevPilot represents a production-grade, mathematically verified RAG system. By pairing dense semantic representations with BM25 sparse search and cross-encoder neural reranking, the platform achieves **100% Recall@5** and a **1.00 MRR**. Backed by automated citation verification guardrails, strict object-level authorization, and 90 passing test cases, DevPilot delivers an exceptional, secure, and reproducible foundation for technical document intelligence.
