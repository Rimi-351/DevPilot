# DevPilot Week 9 Engineering Report: Backend Hardening, Object-Level Authorization & Anti-Hallucination Guardrails

**Milestone:** Week 9 — Harden the Backend  
**Date:** October 2026  
**System Status:** Production Hardened (83 / 83 integration tests passing, 0 warnings, 100% clean Ruff linter checks)  
**Core Deliverables:**
1. 100% Object-Level Authorization Coverage across all API routes (`src/core/security.py`, `src/api/v1/endpoints/`)
2. Chaos & Fault-Injection Error Boundary Test Suite (`tests/test_boundaries.py`)
3. Resilient Ingestion State Machine with Session Rollback (`src/services/ingestion/pipeline.py`, `src/models/processing_job.py`)
4. Composite Multi-Tenant Database Indexes & Deterministic Bounded Pagination (`alembic/versions/`, `src/models/`, `src/schemas/common.py`)
5. Citation Verification Service & Anti-Hallucination Post-Processing Guardrails (`src/core/guardrails.py`, `src/services/rag.py`)

---

## 1. Executive Summary

Following our Week 8 achievement in establishing an empirical state-of-the-art multilingual retrieval champion (**Approach A+B Hybrid: 0.8748 Global MRR, 80.0% Rank #1 hits**), Week 9 transitioned our engineering focus from algorithmic optimization to **production system hardening**.

Modern production AI platforms routinely fail not in model inference itself, but at systemic boundaries:
- **Cross-tenant data leakage** caused by un-scoped foreign key lookups and missing object-level access checks.
- **Cascading background worker crashes** leaving orphaned database entities, half-inserted embeddings, and stale `PENDING` states.
- **Unbounded memory exhaustion attacks** from unconstrained pagination (`limit=1000000`) and un-indexed multi-tenant sorting.
- **LLM citation hallucinations** where generated answers invent non-existent chunk references or fabricate citations to unretrieved documents.

During Week 9, we systematically closed all identified security gaps, added transactional rollback barriers, introduced high-performance composite database indexes, enforced bounded deterministic slicing, and erected strict automated citation verification guardrails.

---

## 2. Object-Level Authorization Across All Routers

Prior to Week 9, authentication verified the cryptographic presence of an `X-API-Key` header, but background job endpoints lacked strict tenancy filtering. In Step 1, we closed this remaining attack surface and enforced **100% object-level authorization coverage** across all six API routers.

### 2.1 Object Authorization Architecture

Every API request undergoes a two-tier security verification:
1. **Tier 1 (Authentication):** `get_current_tenant` extracts the tenant identifier from the `X-API-Key` header, rejecting missing or empty keys with `HTTP 401 Unauthorized`.
2. **Tier 2 (Object-Level Authorization):** `verify_project_tenant_access(project, tenant_id)` inspects the owning `project.tenant_id`. If `project.tenant_id != tenant_id`, the request immediately aborts with `HTTP 403 Forbidden`.

```
Client Request (X-API-Key: Tenant B)
  │
  ▼
[FastAPI Dependency: get_current_tenant] ──► Validates key presence (or HTTP 401)
  │
  ▼
[Database Entity Lookup: Project A] ─────► Fetches entity (or HTTP 404)
  │
  ▼
[verify_project_tenant_access]
  ├── If project.tenant_id == tenant_id   ──► PROCEED (HTTP 200/201)
  └── If project.tenant_id != tenant_id   ──► ABORT with HTTP 403 Forbidden
```

### 2.2 Endpoint Authorization Matrix

| Router | Method & Route | Tenant Security Enforcement | Cross-Tenant Status |
| :--- | :--- | :--- | :---: |
| **Projects** | `POST /api/v1/projects` | Automatically stamps `tenant_id` from authenticated key | `201 Created` |
| **Projects** | `GET /api/v1/projects` | Scopes SQL query: `WHERE Project.tenant_id == tenant_id` | `200 OK` (Tenant Isolated) |
| **Projects** | `GET /api/v1/projects/{id}` | Verified via `verify_project_tenant_access` | `403 Forbidden` |
| **Projects** | `PUT /api/v1/projects/{id}` | Verified via `verify_project_tenant_access` | `403 Forbidden` |
| **Projects** | `DELETE /api/v1/projects/{id}` | Verified via `verify_project_tenant_access` | `403 Forbidden` |
| **Documents** | `POST /api/v1/documents/upload` | Validates target project ownership prior to disk upload | `403 Forbidden` |
| **Documents** | `GET /api/v1/documents` | Requires `project_id`, verifies project ownership | `403 Forbidden` |
| **Documents** | `PATCH /api/v1/documents/{id}` | Verifies document parent project ownership | `403 Forbidden` |
| **Documents** | `DELETE /api/v1/documents/{id}` | Verifies document parent project ownership | `403 Forbidden` |
| **Search** | `POST /api/v1/projects/{id}/search` | Verifies project ownership prior to vector retrieval | `403 Forbidden` |
| **RAG** | `POST /api/v1/projects/{id}/rag` | Verifies project ownership prior to context assembly | `403 Forbidden` |
| **Agent** | `POST /api/v1/projects/{id}/agent/workflow`| Verifies project ownership prior to tool dispatching | `403 Forbidden` |
| **Jobs** | `POST /api/v1/jobs` | Enforces target `project_id` belongs to `tenant_id` | `403 Forbidden` |
| **Jobs** | `GET /api/v1/jobs` *(with filter)* | Verifies filtered `project_id` belongs to `tenant_id` | `403 Forbidden` |
| **Jobs** | `GET /api/v1/jobs` *(unfiltered)* | Scopes query strictly to projects owned by `tenant_id` | `200 OK` (Zero Leaks) |
| **Jobs** | `GET /api/v1/jobs/{job_id}` | Verifies job's parent project belongs to `tenant_id` | `403 Forbidden` |
| **Jobs** | `PATCH /api/v1/jobs/{job_id}/status` | Verifies job's parent project belongs to `tenant_id` | `403 Forbidden` |
| **Jobs** | `DELETE /api/v1/jobs/{job_id}` | Verifies job's parent project belongs to `tenant_id` | `403 Forbidden` |

---

## 3. Resilient Ingestion State Machine & Session Rollback

Long-running background tasks in async Python architectures frequently suffer from silent failures. If an unhandled exception occurs during PDF text extraction, sliding-window chunking, or embedding inference, the database session can become corrupted, leaving `ProcessingJob` stuck in `PENDING` indefinitely while partial `DocumentChunk` records remain orphaned.

### 3.1 State Machine Lifecycle

In Step 2, we designed and encapsulated the background ingestion worker inside [`src/services/ingestion/pipeline.py:process_document_ingestion`](file:///e:/Devpilot/src/services/ingestion/pipeline.py):

```
       [ Upload Endpoint ]
                │
                ▼ Enqueue Background Task
       ┌─────────────────┐
       │     PENDING     │
       └────────┬────────┘
                │ Background Task Picks Up Job
                ▼ Set started_at = datetime.now(UTC)
       ┌─────────────────┐
       │   PROCESSING    │
       └────────┬────────┘
                │
        ┌───────┴───────┐
        │ Extraction    │
        │ Chunking      │
        │ Embeddings    │
        └───────┬───────┘
                │
      Success? ─┤
     ┌──────────┴──────────┐
     ▼ YES                 ▼ NO (Exception Caught)
┌───────────┐         ┌──────────────────────────────┐
│ COMPLETED │         │ 1. await session.rollback()  │
└───────────┘         │ 2. Set status = FAILED       │
                      │ 3. Log exc_info + diagnostics│
                      │ 4. Persist completed_at      │
                      │ 5. await session.commit()    │
                      └──────────────┬───────────────┘
                                     ▼
                              ┌─────────────┐
                              │   FAILED    │
                              └─────────────┘
```

### 3.2 Transactional Integrity Guarantee
When an exception occurs (e.g., corrupt PDF binary stream, out-of-memory embedding error, or invalid payload):
1. **Isolated Session Context:** Document ingestion executes in its own dedicated `async_session_factory()` session.
2. **Explicit Rollback:** `await session.rollback()` immediately invalidates all dirty or half-persisted `DocumentChunk` rows, preventing ghost chunks from polluting the search space.
3. **Structured Failure Reporting:** The job transitions to `JobStatus.FAILED`, setting `completed_at` and populating `error_message` with actionable diagnostic details (`f"{type(exc).__name__}: {str(exc)}"`).
4. **Permanent Failure Persistence:** A clean commit records the failure state so frontend clients polling `GET /api/v1/jobs/{job_id}` receive structured diagnostic telemetry instead of hanging.

---

## 4. Multi-Tenant Composite Database Indexes & Bounded Pagination

### 4.1 Composite Index Design

In multi-tenant relational schemas, filtering by tenant or project while ordering by timestamp causes sequential table scans (`Seq Scan`) and temporary sort buffer overflows as datasets scale.

We authored and applied Alembic migration `4b5c6d7e8f9a_add_job_timestamps_and_composite_indexes.py`, declaring composite `Index` definitions directly on SQLAlchemy models:

1. **`projects` Table:**
   - Composite Index: `ix_projects_tenant_created` on `(tenant_id, created_at)`
   - *Query Optimized:* `SELECT * FROM projects WHERE tenant_id = :tenant_id ORDER BY created_at DESC, id ASC LIMIT :limit OFFSET :skip`
2. **`documents` Table:**
   - Composite Index: `ix_documents_project_created` on `(project_id, created_at)`
   - Composite Index: `ix_documents_project_filename` on `(project_id, filename)`
   - *Query Optimized:* Document listings and deduplication lookups scoped to a target project.
3. **`document_chunks` Table:**
   - Composite Index: `ix_document_chunks_document_index` on `(document_id, chunk_index)`
   - Composite Index: `ix_document_chunks_project_document` on `(project_id, document_id)`
   - *Query Optimized:* Sequential chunk assembly and fast candidate retrieval during RAG.
4. **`processing_jobs` Table:**
   - Composite Index: `ix_processing_jobs_project_status_created` on `(project_id, status, created_at)`
   - Composite Index: `ix_processing_jobs_project_created` on `(project_id, created_at)`
   - *Query Optimized:* Background job status dashboards and worker polling.

### 4.2 Bounded Deterministic Pagination

We eliminated unbound query vulnerabilities (`limit=1000000`) and unstable pagination drift across all list endpoints (`/projects`, `/documents`, `/jobs`):
- **FastAPI / Pydantic Query Bounds:**
  - `skip: int = Query(default=0, ge=0)` — Rejects negative offsets with `HTTP 422 Unprocessable Entity`.
  - `limit: int = Query(default=20, ge=1, le=100)` — Caps maximum page size at 100 items, rejecting zero or excessive limits with `HTTP 422`.
  - Full backward compatibility is preserved for legacy `page` and `page_size` parameters.
- **Deterministic Tie-Breaking Sort:**
  - Standardized on: `ORDER BY created_at DESC, id ASC` across all queries.
  - Ensures identical, repeatable pagination slicing even when multiple records share identical millisecond timestamps, eliminating overlapping or missing records across multi-page traversals.

---

## 5. Citation Integrity & Anti-Hallucination Guardrails

In Step 3, we resolved the vulnerability of un-audited LLM generation by introducing [`src/core/guardrails.py:CitationVerificationService`](file:///e:/Devpilot/src/core/guardrails.py) and [`src/services/rag.py:RagService`](file:///e:/Devpilot/src/services/rag.py).

### 5.1 The Citation Hallucination Problem
When generative models synthesize answers from technical documentation, they frequently exhibit two distinct failure modes:
1. **Out-of-Bounds / Invented Markers:** Answering with citations to indices that were never passed in the context window (e.g., referencing `[99]` when only `[1]`, `[2]`, `[3]` were provided).
2. **Fabricated Source Identifiers:** Inventing non-existent UUIDs or claiming information exists in a file that was not retrieved (e.g., `[chunk: fake-uuid-1234]`).

### 5.2 The Verification & Post-Processing Pipeline

The post-processing guardrail executes synchronously between raw model generation and API response delivery:

```
[ Raw LLM Answer ] ──► Contains valid citations [1] and hallucinated [99], [chunk: fake]
        │
        ▼
[ CitationVerificationService.verify_and_filter_citations ]
  ├── 1. Parse all citation brackets: [N], [N, M], [chunk: UUID], [doc: UUID]
  ├── 2. Map citations against retrieved context chunks:
  │        - Valid: retain chunk reference, link Citation schema
  │        - Invalid: record in invalid_citations_stripped list
  ├── 3. Post-Process Text:
  │        - Strip invalid tags cleanly: "fact [99]." -> "fact."
  │        - Slice multi-brackets: "[1, 99]" -> "[1]"
  │        - Normalize spacing and trailing punctuation
  ├── 4. Calculate Grounding Metrics:
  │        - citation_correctness = valid / (valid + invalid)
  │        - unsupported_claims_rate via sentence token overlap
  │        - is_grounded = (invalid == 0 and unsupported_claims <= 0.20)
        │
        ▼
[ Structured RagResponse ] ──► Returns cleaned answer, citations, and telemetry
```

### 5.3 Mathematical Telemetry Formulations

#### 1. Citation Correctness
Quantifies the ratio of genuine, retrieved citations against all citation attempts generated by the model:

$$\text{citation\_correctness} = \begin{cases} 1.0 & \text{if no citations and negative rejection} \\ \frac{|\text{valid\_citations}|}{|\text{valid\_citations}| + |\text{invalid\_citations}|} & \text{otherwise} \end{cases}$$

#### 2. Unsupported Claims Rate
Measures the percentage of factual claim sentences $S$ in the answer that lack substantive token overlap ($\ge 40\%$) with any retrieved context chunk $C$:

$$\text{overlap\_ratio}(S, C) = \frac{|\text{tokens}(S) \cap \text{tokens}(C)|}{|\text{tokens}(S)|}$$

$$\text{unsupported\_claims\_rate} = \frac{\sum_{S} \mathbb{I}\left(\max_{C} \text{overlap\_ratio}(S, C) < 0.40\right)}{\text{Total claim sentences}}$$

#### 3. Strict Negative Refusal Guarantee
When ungrounded or out-of-domain queries are submitted (e.g., *"What is the secret recipe of Coca-Cola?"* when querying software engineering docs), the system produces a strict polite refusal:
- Response text: `"I do not have enough information in the provided documents to answer this question."`
- `citations = []`, `invalid_citations_stripped = []`
- `is_grounded = True`, `unsupported_claims_rate = 0.0`, `citation_correctness = 1.0`
- Zero hallucinated ingredients, formulas, or speculative facts.

---

## 6. Fault Injection & Error Boundary Test Matrix

All hardening mechanisms were validated using automated chaos and fault injection tests in [`tests/test_boundaries.py`](file:///e:/Devpilot/tests/test_boundaries.py) and [`tests/test_rag.py`](file:///e:/Devpilot/tests/test_rag.py):

| Fault Category | Injection Method | Expected System Behavior | Test Status |
| :--- | :--- | :--- | :---: |
| **Malformed Payload** | Submitting non-UUID strings to path parameters (`/projects/invalid-id`) | Rejection with `HTTP 422 Unprocessable Entity` (no 500 error) | ✅ PASSED |
| **Missing Schema Fields**| Missing required `name` on `POST /projects` | Rejection with `HTTP 422 Unprocessable Entity` | ✅ PASSED |
| **Pagination Underflow**| Submitting `skip=-1` or `limit=0` | Rejection with `HTTP 422 Unprocessable Entity` | ✅ PASSED |
| **Pagination Overflow** | Submitting `limit=1000` | Rejection with `HTTP 422 Unprocessable Entity` | ✅ PASSED |
| **File Size Limit** | Uploading file exceeding `MAX_UPLOAD_SIZE_BYTES` | Rejection with `HTTP 413 Content Too Large` | ✅ PASSED |
| **Unsupported File** | Uploading `.exe` or disallowed binary extensions | Rejection with `HTTP 400 Bad Request` | ✅ PASSED |
| **Missing Project** | Uploading document to non-existent UUID | Rejection with `HTTP 404 Not Found` | ✅ PASSED |
| **Upstream LLM 503** | Upstream provider returns HTTP 503 Service Unavailable | Resilient graceful fallback to deterministic mock | ✅ PASSED |
| **Upstream Timeout** | Simulating hung network call exceeding timeout | Guarded timeout isolation, clean fallback | ✅ PASSED |
| **Worker Parser Crash** | Raising unhandled `RuntimeError` during file extraction | Job transitions to `FAILED`, persists error, rolls back DB | ✅ PASSED |
| **Cross-Tenant Attack** | Tenant B attempts GET/PATCH/DELETE on Tenant A project/job | Rejection with `HTTP 403 Forbidden` | ✅ PASSED |
| **Job List Leakage** | Tenant B lists jobs without project filter | Zero jobs belonging to Tenant A leaked in response | ✅ PASSED |
| **Invented Citations** | LLM response citing out-of-bounds `[99]` and fake UUID | Guardrail strips invalid markers, flags `is_grounded=False` | ✅ PASSED |
| **Negative Query** | Asking for *"Coca-Cola secret recipe"* against technical docs | Returns polite refusal, 0 citations, 0 hallucinated facts | ✅ PASSED |

---

## 7. Verification & Repository Hygiene

The hardened repository was verified using the full test harness and static analysis tools:

### Pytest Execution Summary
```text
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

============================= 83 passed in 49.61s =============================
```

### Static Analysis
```bash
python -m ruff check src/ tests/ scripts/
# Output: All checks passed! (0 errors, 0 warnings)
```

---

## 8. Summary of Week 9 Production Hardening Achievements

1. **Enterprise Multi-Tenancy:** Guaranteed 100% object-level isolation across all 6 core routers, closing all authorization leakage vectors.
2. **Deterministic Query Performance:** Eliminated sequential table scans and memory exhaustion vulnerabilities with 6 composite database indexes and strictly bounded pagination.
3. **Resilient Background Execution:** Established guaranteed lifecycle reporting (`PENDING` $\rightarrow$ `PROCESSING` $\rightarrow$ `COMPLETED` / `FAILED`) with transactional session rollback.
4. **Citation Provenance & Anti-Hallucination:** Guarded RAG generation with automated post-processing that eliminates invented citations and exports grounding metrics (`is_grounded`, `citation_correctness`, `unsupported_claims_rate`).
5. **Zero-Regression Test Suite:** Expanded test suite from 61 to **83 passing tests** with 100% green status and zero linter warnings.
