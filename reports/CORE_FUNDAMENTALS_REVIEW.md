# DevPilot Core CS & Backend Fundamentals Review Guide
## Technical Interview Revision: DSA, SQL Optimization, Concurrency & RESTful Architecture

**Document Version:** 1.0.0  
**Target Roles:** Senior Backend Engineer, Distributed Systems Engineer, AI Platform Architect  
**Purpose:** Rapid technical interview revision mapping theoretical computer science principles directly to production code patterns inside DevPilot.

---

## Table of Contents

1. [Executive Overview: Bridging Theory to Production Systems](#1-executive-overview-bridging-theory-to-production-systems)
2. [Section 1: High-Yield DSA Patterns in Production](#section-1-high-yield-dsa-patterns-in-production)
   - [1.1 Sliding Window Algorithm (Document Chunking with Overlap)](#11-sliding-window-algorithm-document-chunking-with-overlap)
   - [1.2 Hash Maps & Inverted Indexes (BM25 Lexical Retrieval & RRF)](#12-hash-maps--inverted-indexes-bm25-lexical-retrieval--rrf)
   - [1.3 Heaps / Priority Queues & Top-K Selection (Candidate Slicing)](#13-heaps--priority-queues--top-k-selection-candidate-slicing)
   - [1.4 Directed Graphs & Finite State Machines (Bounded Agentic FSM)](#14-directed-graphs--finite-state-machines-bounded-agentic-fsm)
3. [Section 2: SQL Query Optimization & Relational Modeling](#section-2-sql-query-optimization--relational-modeling)
   - [2.1 Composite B-Tree Indexes & The Leftmost Prefix Rule](#21-composite-b-tree-indexes--the-leftmost-prefix-rule)
   - [2.2 Covering Indexes & Index Range Scans](#22-covering-indexes--index-range-scans)
   - [2.3 Analytical Window Functions & Partitioning](#23-analytical-window-functions--partitioning)
   - [2.4 Recursive CTEs for Self-Referencing Document Hierarchies](#24-recursive-ctes-for-self-referencing-document-hierarchies)
4. [Section 3: Database Transactions, Concurrency & ACID Guarantees](#section-3-database-transactions-concurrency--acid-guarantees)
   - [3.1 ANSI SQL Transaction Isolation Levels & Concurrency Anomalies](#31-ansi-sql-transaction-isolation-levels--concurrency-anomalies)
   - [3.2 Transaction Rollback Boundaries & Ghost Chunk Prevention](#32-transaction-rollback-boundaries--ghost-chunk-prevention)
   - [3.3 PostgreSQL MVCC vs. SQLite File Locking & Concurrency](#33-postgresql-mvcc-vs-sqlite-file-locking--concurrency)
5. [Section 4: HTTP Semantics & RESTful API Architecture](#section-4-http-semantics--restful-api-architecture)
   - [4.1 HTTP Method Idempotency & Safety](#41-http-method-idempotency--safety)
   - [4.2 Precise HTTP Status Code Taxonomy](#42-precise-http-status-code-taxonomy)
   - [4.3 Two-Tier Security & BOLA Prevention (OWASP API1:2023)](#43-two-tier-security--bola-prevention-owasp-api12023)
6. [Section 5: High-Yield Interview Revision Cheatsheet](#section-5-high-yield-interview-revision-cheatsheet)

---

## 1. Executive Overview: Bridging Theory to Production Systems

In senior backend interviews, top candidates stand out by demonstrating how fundamental computer science concepts (Data Structures, Algorithms, Relational Algebra, Operating Systems, Networking) solve real engineering bottlenecks.

```
Theoretical CS Principle               DevPilot Production Implementation
──────────────────────────────         ──────────────────────────────────────────────────
Sliding Window (Array/String)     ──►  Character-level sliding window chunker (512/64 overlap)
Inverted Index & Hash Map         ──►  BM25Okapi inverted index & RRF score aggregation in O(N)
Min-Heap / Priority Queue         ──►  Top-K candidate selection (O(N log K) vs O(N log N))
Directed Acyclic Graph & FSM      ──►  4-phase bounded agentic FSM (SEARCH -> INSPECT -> ...)
B-Tree Leftmost Prefix Rule       ──►  Composite indexes (tenant_id, created_at) avoiding filesort
ACID Rollback Isolation           ──►  await session.rollback() preventing partial ghost chunks
HTTP Idempotency & Status Codes   ──►  Deterministic REST APIs, 401 perimeter, 403 BOLA defense
```

---

## Section 1: High-Yield DSA Patterns in Production

### 1.1 Sliding Window Algorithm (Document Chunking with Overlap)

#### The Problem:
Splitting arbitrary text into fixed-size segments risks severing sentences and losing semantic context across chunk boundaries.

#### DevPilot Implementation (`src/services/chunker.py`):
```python
def chunk_text(
    text: str, 
    chunk_size: int = 512, 
    chunk_overlap: int = 64
) -> list[TextChunk]:
    """Sliding window chunking preserving start and end character offsets."""
    if not text or not text.strip():
        return []
    
    stride = max(1, chunk_size - chunk_overlap)
    chunks: list[TextChunk] = []
    start = 0
    total_len = len(text)
    index = 1

    while start < total_len:
        end = min(start + chunk_size, total_len)
        chunk_content = text[start:end]
        chunks.append(TextChunk(
            index=index,
            content=chunk_content,
            start_offset=start,
            end_offset=end,
        ))
        index += 1
        start += stride

    return chunks
```

#### Complexity & Algorithmic Invariants:
- **Time Complexity:** $O(L)$ where $L$ is the length of the string. Each character is visited at most $\frac{\text{chunk\_size}}{\text{stride}} \approx 1.14$ times for $(512, 64)$.
- **Space Complexity:** $O(L)$ auxiliary memory to store string slices.
- **Invariants:**
  - $\text{stride} = \text{chunk\_size} - \text{chunk\_overlap} = 512 - 64 = 448$.
  - For chunk $i$ and chunk $i+1$, the overlapping substring length is exactly $\min(64, \text{remaining})$.
  - $\text{start\_offset}_{i+1} = \text{start\_offset}_i + \text{stride}$.

---

### 1.2 Hash Maps & Inverted Indexes (BM25 Lexical Retrieval & RRF)

#### The Problem:
Evaluating lexical keyword relevance across thousands of text chunks in real time requires fast term-frequency lookups without scanning the entire corpus.

#### DevPilot Implementation (`src/services/retrieval/bm25.py` & `hybrid.py`):
1. **Inverted Index Data Structure:**
   - A dictionary mapping each unique token to its document frequency and per-document term frequencies:
     ```python
     # token -> {doc_id: term_frequency}
     inverted_index: dict[str, dict[str, int]]
     # doc_id -> total_tokens
     doc_lengths: dict[str, int]
     ```
2. **Reciprocal Rank Fusion (RRF) in $O(N)$ Time:**
   ```python
   def reciprocal_rank_fusion(
       dense_ranked_ids: list[str],
       sparse_ranked_ids: list[str],
       k: int = 60,
   ) -> list[tuple[str, float]]:
       """Fuse dense and sparse rankings in O(N) using hash map accumulation."""
       rrf_scores: dict[str, float] = {}

       for rank, doc_id in enumerate(dense_ranked_ids, start=1):
           rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

       for rank, doc_id in enumerate(sparse_ranked_ids, start=1):
           rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

       # Sort aggregated dictionary by score descending
       return sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
   ```

#### Complexity & Invariants:
- **Time Complexity:** $O(N_1 + N_2 + M \log M)$ where $N_1, N_2 \le 50$ are candidate list lengths, and $M \le N_1 + N_2$ is unique document count. In production, this executes in $<0.05\text{ ms}$.
- **Space Complexity:** $O(M)$ hash map memory.
- **Scale-Invariant Invariant:** RRF replaces volatile score distributions (cosine $[-1, 1]$ vs BM25 $[0, \infty)$) with monotonically decreasing ordinal rank weights $\frac{1}{k + rank}$.

---

### 1.3 Heaps / Priority Queues & Top-K Selection (Candidate Slicing)

#### The Problem:
When retrieving the top $K=5$ chunks out of $N=10,000$ scored candidates, a full array sort costs $O(N \log N)$.

#### Min-Heap Optimization ($O(N \log K)$):
Instead of sorting all $N$ elements:
1. Maintain a **Min-Heap of capacity $K$**.
2. For each candidate $(score, chunk)$:
   - If heap size $< K$: push $(score, chunk)$.
   - Else if $score > \text{heap}[0].score$: pop the smallest element and push candidate.
3. At termination, the heap contains the exact top $K$ largest elements.

```python
import heapq

def select_top_k_candidates(candidates: list[tuple[float, str]], k: int) -> list[tuple[float, str]]:
    """O(N log K) Top-K selection using a Min-Heap."""
    if not candidates or k <= 0:
        return []
    if k >= len(candidates):
        return sorted(candidates, key=lambda x: x[0], reverse=True)

    # Use heapq.nlargest which implements an optimized min-heap under the hood
    return heapq.nlargest(k, candidates, key=lambda x: x[0])
```

#### Complexity Comparison:
| Approach | Time Complexity | Auxiliary Space | Best Used When |
| :--- | :---: | :---: | :--- |
| **Full Sort (`sorted()`)** | $O(N \log N)$ | $O(N)$ | $N$ is small ($N \le 100$) |
| **Min-Heap (`heapq.nlargest`)** | $O(N \log K)$ | $O(K)$ | $N \gg K$ ($N = 100,000$, $K = 5$) |
| **Quickselect (Hoare)** | $O(N)$ avg, $O(N^2)$ worst | $O(1)$ | Streaming in-place partition |

---

### 1.4 Directed Graphs & Finite State Machines (Bounded Agentic FSM)

#### The Problem:
Autonomous LLM agents easily fall into infinite execution loops, hallucinatory phase skipping, or circular tool calls.

#### DevPilot Implementation (`src/services/agent/workflow.py`):
DevPilot models research workflows as a **Deterministic Finite State Machine (FSM)** governed by strict transition invariants:

```
[SEARCH] ──(Queries >= 1)──► [INSPECT] ──(Chunks >= 1)──► [SUMMARIZE] ──► [PROPOSE]
   ▲                           │                              │               │
   │ (Refine Search)           │                              │               ▼
   └───────────────────────────┴──────────────────────────────┘           [TERMINAL]
```

```python
VALID_TRANSITIONS = {
    AgentPhase.SEARCH: {AgentPhase.SEARCH, AgentPhase.INSPECT},
    AgentPhase.INSPECT: {AgentPhase.SEARCH, AgentPhase.INSPECT, AgentPhase.SUMMARIZE},
    AgentPhase.SUMMARIZE: {AgentPhase.INSPECT, AgentPhase.SUMMARIZE, AgentPhase.PROPOSE},
    AgentPhase.PROPOSE: set(),  # Terminal state
}
```

#### Invariants & Safety Guardrails:
1. **Loop Bound Invariant:** Hard cap of $\text{MAX\_STEPS} = 5$. A monotonically incrementing counter aborts execution if an agent attempts a 6th iteration.
2. **Phase Boundary Guard:** The dispatcher rejects tool invocations that violate phase permissions (e.g. calling `propose_solution` while in `SEARCH` raises `PhaseViolationError`).
3. **DAG Property:** The transition matrix guarantees a Directed Acyclic Graph (DAG) path toward the terminal `PROPOSE` phase.

---

## Section 2: SQL Query Optimization & Relational Modeling

### 2.1 Composite B-Tree Indexes & The Leftmost Prefix Rule

#### The Rule:
A composite B-Tree index on columns $(A, B, C)$ can serve queries filtering on:
- $(A)$
- $(A, B)$
- $(A, B, C)$
It **cannot** serve queries filtering only on $(B)$ or $(B, C)$ without a full index scan.

#### DevPilot Production Composite Indexes:
```python
# Project entity (src/models/project.py)
Index("ix_projects_tenant_created", "tenant_id", "created_at")

# ProcessingJob entity (src/models/processing_job.py)
Index("ix_processing_jobs_project_status_created", "project_id", "status", "created_at")
```

#### Why Column Order Matters (Eliminating Filesort):
Consider the query:
```sql
SELECT * FROM projects 
WHERE tenant_id = 'tenant-xyz' 
ORDER BY created_at DESC 
LIMIT 20;
```
1. **If indexed on `(tenant_id)` alone:** The database jumps to `tenant_id = 'tenant-xyz'`, loads all 10,000 rows into memory, and executes an expensive **Filesort** (`Using filesort` in `EXPLAIN`).
2. **With composite `(tenant_id, created_at)`:** The index entries for `'tenant-xyz'` are **already physically stored in sorted order by `created_at`** in the B-Tree leaf pages. The engine traverses the B-Tree in reverse and returns the first 20 rows immediately. **Zero filesort, $O(\log N)$ execution!**

---

### 2.2 Covering Indexes & Index Range Scans

#### Concept:
A query is **covered** by an index if all requested columns exist inside the B-Tree index nodes, allowing the database engine to return data directly from the index without reading the underlying heap/table pages (**Index-Only Scan**).

#### DevPilot Implementation:
```python
Index("ix_document_chunks_document_index", "document_id", "chunk_index")
```
When retrieving chunk indices for a document:
```sql
SELECT chunk_index FROM document_chunks 
WHERE document_id = :doc_id 
ORDER BY chunk_index ASC;
```
The query planner satisfies this entirely from the index tree leaf nodes in $O(K)$ time without touching table storage.

---

### 2.3 Analytical Window Functions & Partitioning

#### Concept:
Window functions calculate aggregate values over a partition of rows without collapsing the result set like `GROUP BY`.

#### Canonical Pattern: `DENSE_RANK()` vs `RANK()` vs `ROW_NUMBER()`
```sql
SELECT 
    project_id,
    id AS job_id,
    duration_seconds,
    ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY duration_seconds ASC) AS row_num,
    RANK() OVER (PARTITION BY project_id ORDER BY duration_seconds ASC) AS rank_val,
    DENSE_RANK() OVER (PARTITION BY project_id ORDER BY duration_seconds ASC) AS dense_rank_val
FROM processing_jobs;
```

| Duration | `ROW_NUMBER()` | `RANK()` (Gaps) | `DENSE_RANK()` (No Gaps) |
| :---: | :---: | :---: | :---: |
| 1.2s | 1 | 1 | 1 |
| 1.2s | 2 | 1 | 1 |
| 2.5s | 3 | 3 ⚠️ | **2** ✅ |
| 3.1s | 4 | 4 | 3 |

*Key Interview Takeaway:* To find "Top 3 distinct salaries" or "Top 3 fastest jobs", always use `DENSE_RANK() <= 3`.

---

### 2.4 Recursive CTEs for Self-Referencing Document Hierarchies

#### Syntax Anatomy:
```sql
WITH RECURSIVE TreeCTE AS (
    -- 1. Anchor Member (Base Case: Target Node)
    SELECT id, parent_id, title, 0 AS depth
    FROM documents WHERE id = :target_id

    UNION ALL

    -- 2. Recursive Member (Traverse Parent References)
    SELECT p.id, p.parent_id, p.title, t.depth + 1
    FROM documents p
    JOIN TreeCTE t ON p.id = t.parent_id
)
SELECT * FROM TreeCTE ORDER BY depth DESC;
```
- **Execution Lifecycle:** The engine seeds working table with the Anchor Member, joins the Recursive Member iteratively until the working table is empty, and performs a final `UNION ALL`.

---

## Section 3: Database Transactions, Concurrency & ACID Guarantees

### 3.1 ANSI SQL Transaction Isolation Levels & Concurrency Anomalies

Transactions must satisfy **ACID**: Atomicity, Consistency, Isolation, Durability.

```
Anomalies:
1. Dirty Read       : Transaction A reads uncommitted changes from Transaction B.
2. Non-Repeatable   : Transaction A re-reads a row and finds values modified by Transaction B.
3. Phantom Read     : Transaction A re-runs a range query and finds new rows added by Transaction B.
4. Write Skew       : Two concurrent transactions read overlapping state and write non-conflicting
                      updates that jointly violate a business invariant.
```

| Isolation Level | Dirty Read | Non-Repeatable Read | Phantom Read | Write Skew | Implementation Mechanism |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Read Uncommitted** | Possible | Possible | Possible | Possible | Read without locks |
| **Read Committed** *(PostgreSQL Default)* | ❌ Prevented | Possible | Possible | Possible | Read snapshot at query start |
| **Repeatable Read** | ❌ Prevented | ❌ Prevented | ❌ Prevented *(in Postgres MVCC)* | Possible | Read snapshot at transaction start |
| **Serializable** | ❌ Prevented | ❌ Prevented | ❌ Prevented | ❌ Prevented | Strict 2-Phase Locking (S2PL) or SSI |

---

### 3.2 Transaction Rollback Boundaries & Ghost Chunk Prevention

#### The Problem:
In background document ingestion, text extraction, chunking, embedding, and SQL inserts occur in sequence. If embedding generation times out halfway, what happens to staged chunk entities?

```
[FastAPI Background Worker]
            │
            ▼
   async with factory() as session:
       try:
           chunks = chunk_text(...)
           embeddings = await generate_embeddings(...)
           session.add_all(db_chunks)  <── Staged in SQLAlchemy Identity Map!
           await session.commit()
       except Exception:
           await session.rollback()    <── PURGES identity map and transaction log!
           # Record FAILED state in separate clean transaction
```

#### Why `await session.rollback()` is Critical:
- SQLAlchemy tracks objects in memory via an **Identity Map**.
- Calling `session.add_all(db_chunks)` marks those entities as dirty/pending.
- If an exception occurs and the developer catches it without calling `rollback()`, any subsequent query or commit will **flush the dirty chunks to disk**, creating orphaned "ghost chunks" belonging to a failed document.
- `await session.rollback()` sends an explicit `ROLLBACK` to the database engine and purges the session cache.

---

### 3.3 PostgreSQL MVCC vs. SQLite File Locking & Concurrency

1. **PostgreSQL Multi-Version Concurrency Control (MVCC):**
   - Updates and deletes do not overwrite data in-place; they create a new tuple version with `xmin` (creation transaction ID) and `xmax` (deletion transaction ID).
   - **Readers never block writers, and writers never block readers.**
   - Dead tuples are reclaimed asynchronously via `VACUUM`.
2. **SQLite File-Level Locking:**
   - In standard rollback journal mode, writing locks the entire database file (`SQLITE_BUSY`).
   - DevPilot enables **WAL (Write-Ahead Logging)** mode for SQLite, which allows concurrent readers alongside a single writer.

---

## Section 4: HTTP Semantics & RESTful API Architecture

### 4.1 HTTP Method Idempotency & Safety

- **Safe Method:** Does not alter server state (Read-only).
- **Idempotent Method:** Making $N$ identical requests produces the exact same server state as making 1 request ($f(f(x)) = f(x)$).

| Method | Safe? | Idempotent? | DevPilot Endpoint Example | RFC Semantics |
| :---: | :---: | :---: | :--- | :--- |
| `GET` | **Yes** | **Yes** | `GET /api/v1/projects/{id}` | Cacheable, zero side-effects |
| `POST` | No | No | `POST /api/v1/projects` | Creates new resource; returns `201 Created` |
| `PATCH` | No | No | `PATCH /api/v1/projects/{id}` | Partial update of entity fields |
| `PUT` | No | **Yes** | `PUT /api/v1/documents/{id}` | Complete replacement of entity |
| `DELETE` | No | **Yes** | `DELETE /api/v1/projects/{id}` | Deletes entity; deleting twice still leaves entity gone |

---

### 4.2 Precise HTTP Status Code Taxonomy

DevPilot maps application domain exceptions to precise HTTP status codes:

| Status Code | RFC Meaning | DevPilot Trigger Scenario | Code Reference |
| :---: | :--- | :--- | :--- |
| **`200 OK`** | Standard successful response | Successful retrieval, search, RAG synthesis | `api/v1/endpoints/search.py` |
| **`201 Created`** | New entity created | Project created, document record provisioned | `api/v1/endpoints/projects.py` |
| **`400 Bad Request`** | Malformed request syntax | Slicing bounds violated (`skip < 0`) | `src/main.py:value_error_handler` |
| **`401 Unauthorized`** | Missing/invalid authentication | Missing or blank `X-API-Key` header | `src/core/security.py:get_current_tenant` |
| **`403 Forbidden`** | Authenticated, but not authorized | Caller tenant mismatch (`owner != current_api_key`) or Demo write | `src/core/security.py:verify_project_tenant_access` |
| **`404 Not Found`** | Resource does not exist | `project_id` or `document_id` does not exist | `src/services/job.py` |
| **`409 Conflict`** | Resource state collision | Duplicate document SHA-256 upload | `src/main.py:conflict_error_handler` |
| **`422 Unprocessable`** | Schema validation failure | Missing required JSON body field (Pydantic) | FastAPI default exception handler |
| **`503 Service Unavail`**| Upstream service outage | LLM API provider timeout or network drop | `src/services/llm.py` |

---

### 4.3 Two-Tier Security & BOLA Prevention (OWASP API1:2023)

#### The Vulnerability (BOLA / IDOR):
Broken Object Level Authorization occurs when an API endpoint relies on user-supplied IDs (e.g. `/projects/{uuid}`) without verifying whether the authenticated user owns that specific object.

#### DevPilot Two-Tier Defense Model:
```
Request: GET /api/v1/projects/550e8400-e29b-41d4-a716-446655440000
Header : X-API-Key: tenant_b_key

Tier 1: Gateway Perimeter Authentication
├── Validates X-API-Key is present and well-formed.
└── Sets request state: authenticated_tenant = 'tenant_b_key'.
    (If missing -> HTTP 401 Unauthorized)

Tier 2: Object-Level Authorization
├── Fetches project entity from database.
├── Compares: project.tenant_id ('tenant_a_key') == authenticated_tenant ('tenant_b_key').
└── Mismatch detected! -> HTTP 403 Forbidden. Execution HALTS.
```

---

## Section 5: High-Yield Interview Revision Cheatsheet

### 60-Second Flashcard Review:

1. **Why does RRF use $k=60$?**  
   It smooths rank transitions ($\frac{1}{61}$ vs $\frac{1}{62}$) so that documents ranked in the top-10 of *both* dense and sparse lists score higher than an outlier ranked #1 in only one list.
2. **Why put `tenant_id` before `created_at` in composite indexes?**  
   The leftmost prefix rule isolates the tenant's partition in $O(\log N)$ and streams pre-sorted records directly off the index leaf pages without an in-memory filesort.
3. **What is the difference between `RANK()` and `DENSE_RANK()`?**  
   `RANK()` leaves gaps after ties ($1, 1, 3$); `DENSE_RANK()` assigns contiguous integers without gaps ($1, 1, 2$), making it ideal for "Top 3 unique values".
4. **How do you prevent ghost chunks during worker failure?**  
   Wrap database chunk staging in `try...except` and immediately execute `await session.rollback()` to flush the SQLAlchemy identity map before committing the `FAILED` state.
5. **What is the difference between HTTP 401 and HTTP 403?**  
   `401 Unauthorized` means *"I do not know who you are (missing/invalid credentials)"*. `403 Forbidden` means *"I know who you are, but you do not have permission to access this object"*.
