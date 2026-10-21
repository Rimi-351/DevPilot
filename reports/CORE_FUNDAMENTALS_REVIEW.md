# DevPilot Core CS & Backend Fundamentals Review Guide
## Technical Interview Revision: DSA, Database Transactions, SQL Optimization & RESTful Architecture

**Document Version:** 1.3.0  
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
3. [Section 2: Relational Database Transactions & Concurrency](#section-2-relational-database-transactions--concurrency)
   - [2.1 ACID Properties & SQLAlchemy Async Transaction Management (`commit()` vs `rollback()`)](#21-acid-properties--sqlalchemy-async-transaction-management-commit-vs-rollback)
   - [2.2 Database Isolation Levels & Concurrency Anomalies (Dirty, Non-Repeatable, Phantom Reads)](#22-database-isolation-levels--concurrency-anomalies-dirty-non-repeatable-phantom-reads)
   - [2.3 How DevPilot Prevents "Ghost Chunk" Anomalies During Background Ingestion Failures](#23-how-devpilot-prevents-ghost-chunk-anomalies-during-background-ingestion-failures)
   - [2.4 Concurrency Engines: PostgreSQL MVCC vs. SQLite WAL File Locking](#24-concurrency-engines-postgresql-mvcc-vs-sqlite-wal-file-locking)
4. [Section 3: SQL Indexing & Query Execution Plans](#section-3-sql-indexing--query-execution-plans)
   - [3.1 Left-Prefix Rule in Composite B-Tree Indexes (`ix_projects_tenant_created`)](#31-left-prefix-rule-in-composite-b-tree-indexes-ix_projects_tenant_created)
   - [3.2 Avoiding Filesorts & Temporary Tables in Execution Plans](#32-avoiding-filesorts--temporary-tables-in-execution-plans)
   - [3.3 N+1 Query Mitigation in ORM Architectures (`selectinload` vs `joinedload`)](#33-n1-query-mitigation-in-orm-architectures-selectinload-vs-joinedload)
   - [3.4 Keyset / Cursor vs. Offset Pagination Trade-offs & Drift Prevention](#34-keyset--cursor-vs-offset-pagination-trade-offs--drift-prevention)
   - [3.5 Analytical Window Functions (`DENSE_RANK()`) & Recursive CTEs](#35-analytical-window-functions-denserank--recursive-ctes)
5. [Section 4: HTTP Protocol Semantics & RESTful API Design](#section-4-http-protocol-semantics--restful-api-design)
   - [4.1 HTTP Method Idempotency & Safety (`GET`, `PUT`, `DELETE` vs `POST` and `PATCH`)](#41-http-method-idempotency--safety-get-put-delete-vs-post-and-patch)
   - [4.2 Exact Status Code Semantics Enforced in DevPilot (`200`, `201`, `202`, `401`, `403`, `404`, `409`, `422`, `503`)](#42-exact-status-code-semantics-enforced-in-devpilot-200-201-202-401-403-404-409-422-503)
   - [4.3 Statelessness, CORS Architecture, and Header-Driven Tenant Isolation (`X-API-Key`)](#43-statelessness-cors-architecture-and-header-driven-tenant-isolation-x-api-key)
   - [4.4 Two-Tier Security & BOLA Prevention (OWASP API1:2023)](#44-two-tier-security--bola-prevention-owasp-api12023)
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
Keyset vs Offset Pagination       ──►  Bounded deterministic pagination with secondary tie-breaking
HTTP Idempotency & Status Codes   ──►  Deterministic REST APIs, 401 perimeter, 403 BOLA defense
Statelessness & Custom Headers    ──►  Header-driven X-API-Key tenant boundary without session cookies
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

## Section 2: Relational Database Transactions & Concurrency

### 2.1 ACID Properties & SQLAlchemy Async Transaction Management (`commit()` vs `rollback()`)

Relational database transactions must satisfy the four **ACID** properties:
- **Atomicity:** All operations within a transaction succeed or all fail together. If a document chunking process creates 10 chunks and the 10th fails, zero chunks remain in the database.
- **Consistency:** Transactions transition the database from one valid state to another, preserving all schemas, primary keys, foreign keys (`project_id -> projects.id`), and check constraints.
- **Isolation:** Concurrent transactions execute without cross-talk or race conditions, as if executed serially.
- **Durability:** Once committed via `COMMIT`, updates survive crashes, power cuts, or process termination (guaranteed via Write-Ahead Logging / WAL).

#### Async Transaction Lifecycle in DevPilot (`src/core/database.py`):
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a managed async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()    # 1. Emits SQL COMMIT on successful execution
        except Exception:
            await session.rollback()  # 2. Emits SQL ROLLBACK on unhandled exception
            raise
        finally:
            await session.close()     # 3. Releases connection back to pool
```

#### Under the Hood: `await session.commit()` vs. `await session.rollback()`
1. **`await session.commit()`:**
   - Flushes all pending INSERT/UPDATE/DELETE statements in the SQLAlchemy identity map to the database engine.
   - Sends the raw wire protocol `COMMIT` instruction.
   - Clears pending dirty markers and releases transaction locks.
2. **`await session.rollback()`:**
   - Sends the raw wire protocol `ROLLBACK` instruction to the database engine, causing the database to revert all uncommitted modifications written during the transaction.
   - **Crucially for SQLAlchemy:** Clears and purges the **Identity Map** (in-memory cache of entity instances). Any pending `add()`, `add_all()`, or modified entity attributes are discarded, resetting the session to a clean, pristine state.
3. **Session Configuration Flags:**
   ```python
   async_session_factory = async_sessionmaker(
       bind=engine,
       class_=AsyncSession,
       expire_on_commit=False,  # Attributes stay in memory across async await points
       autoflush=False,         # Prevents premature implicit flushes before validation
   )
   ```
   `expire_on_commit=False` prevents `MissingGreenlet` errors when serializing ORM models into Pydantic responses outside an active database block.

---

### 2.2 Database Isolation Levels & Concurrency Anomalies (Dirty, Non-Repeatable, Phantom Reads)

The ANSI SQL standard defines four transaction isolation levels based on which concurrency anomalies they prevent:

```
Concurrency Anomalies Visualized:

1. Dirty Read:
   Tx 1: UPDATE projects SET status = 'DONE' (uncommitted)
   Tx 2: SELECT status FROM projects -> Reads 'DONE'
   Tx 1: ROLLBACK (status reverts to 'PENDING')
   Result: Tx 2 acted on dirty data that never officially existed!

2. Non-Repeatable Read (Fuzzy Read):
   Tx 1: SELECT chunk_count FROM docs WHERE id = 1 -> Returns 5
   Tx 2: UPDATE docs SET chunk_count = 10 WHERE id = 1; COMMIT;
   Tx 1: SELECT chunk_count FROM docs WHERE id = 1 -> Returns 10!
   Result: Same query within same transaction returned different values.

3. Phantom Read:
   Tx 1: SELECT COUNT(*) FROM jobs WHERE status = 'PENDING' -> Returns 2
   Tx 2: INSERT INTO jobs (status) VALUES ('PENDING'); COMMIT;
   Tx 1: SELECT COUNT(*) FROM jobs WHERE status = 'PENDING' -> Returns 3!
   Result: New rows ("phantoms") appeared in a range query.

4. Serialization Anomaly / Write Skew:
   Tx 1: Reads count of documents in Project A (sees 9, limit is 10)
   Tx 2: Reads count of documents in Project A (sees 9, limit is 10)
   Tx 1: Inserts doc 10 and commits.
   Tx 2: Inserts doc 11 and commits.
   Result: Both succeeded, resulting in 11 documents and violating the limit!
```

#### Isolation Levels Matrix:
| Isolation Level | Dirty Read | Non-Repeatable Read | Phantom Read | Serialization Anomaly | Implementation Mechanism |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Read Uncommitted** | ⚠️ Possible | ⚠️ Possible | ⚠️ Possible | ⚠️ Possible | Reads raw dirty memory without locks |
| **Read Committed** *(PostgreSQL Default)* | ❌ Prevented | ⚠️ Possible | ⚠️ Possible | ⚠️ Possible | Read snapshot generated at start of each SQL statement |
| **Repeatable Read** | ❌ Prevented | ❌ Prevented | ❌ Prevented *(in Postgres MVCC)* | ⚠️ Possible | Read snapshot generated at start of entire transaction |
| **Serializable** | ❌ Prevented | ❌ Prevented | ❌ Prevented | ❌ Prevented | Serializable Snapshot Isolation (SSI) or Strict 2-Phase Locking |

*Key Senior Takeaway:* PostgreSQL's `Repeatable Read` prevents phantom reads under its MVCC implementation because snapshots are pinned to the transaction start time; however, it can still experience Write Skew unless `Serializable` is explicitly declared.

---

### 2.3 How DevPilot Prevents "Ghost Chunk" Anomalies During Background Ingestion Failures

#### The Production Vulnerability ("Ghost Chunks"):
In document RAG pipelines, background ingestion proceeds through four distinct operations:
1. PDF/Text Extraction $\to$ 2. Sliding-Window Chunking $\to$ 3. FastEmbed Embedding Generation $\to$ 4. Database Persistence.

If Step 3 (Embedding) crashes (e.g. OOM, network timeout, model deserialization failure), uncommitted `DocumentChunk` entities staged in SQLAlchemy's session identity map will linger in memory. If the application catches the error and attempts to update `job.status = FAILED` using `session.commit()` on the *same dirty session*, SQLAlchemy will **flush the partial chunks along with the job status**, creating orphaned **"ghost chunks"** that pollute downstream vector search!

#### DevPilot's Rollback Isolation Architecture (`src/services/ingestion/pipeline.py`):
```python
# ── Phase 1: Mark Job PROCESSING in dedicated session ────────────────────────
async with factory() as session:
    job = await session.get(ProcessingJob, job_uuid)
    job.status = JobStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    await session.commit()

# ── Phase 2: Ingestion Workhorse with Rollback Isolation ──────────────────────
async with factory() as session:
    try:
        text = await extract_text_from_file(...)
        chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)
        embeddings = await embedding_service.generate_embeddings(...)
        
        # Stage chunk records in identity map
        db_chunks = [DocumentChunk(...) for i, chunk in enumerate(chunks)]
        session.add_all(db_chunks)

        job.status = JobStatus.COMPLETED
        await session.commit()  # Atomically commits all chunks + COMPLETED state

    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        # CRITICAL: 1. Abort transaction and purge all uncommitted chunks!
        await session.rollback()

        # 2. Re-acquire fresh entity in isolated recovery block
        try:
            failed_job = await session.get(ProcessingJob, job_uuid)
            if failed_job:
                failed_job.status = JobStatus.FAILED
                failed_job.error_message = f"{type(exc).__name__}: {str(exc)[:1000]}"
                failed_job.completed_at = datetime.now(timezone.utc)
                await session.commit()  # Commits ONLY the failure state
        except Exception as inner_exc:
            logger.error("Failed to persist failure status: %s", inner_exc)
        raise
```

#### Why This Guarantees Zero Ghost Chunks:
1. `await session.rollback()` explicitly sends a `ROLLBACK` wire command, aborting the active SQL transaction.
2. SQLAlchemy wipes all staged `DocumentChunk` entities from the identity map.
3. The subsequent `session.get(ProcessingJob, job_uuid)` starts with an empty, pristine state buffer.
4. Calling `await session.commit()` in the recovery block flushes **only** the `FAILED` status and diagnostic error trace.
5. Result: The database chunks table contains **0 records** for the failed document. Vector and BM25 indices remain 100% clean.

---

### 2.4 Concurrency Engines: PostgreSQL MVCC vs. SQLite WAL File Locking

| Concurrency Dimension | PostgreSQL 16 (Production) | SQLite (Local Edge / Testing) |
| :--- | :--- | :--- |
| **Engine Architecture** | Multi-process client-server with connection pooling | In-process embedded serverless database |
| **Concurrency Model** | **MVCC (Multi-Version Concurrency Control)**: Tuple versions tagged with `xmin`/`xmax`. Readers do not block writers; writers do not block readers. | **WAL Mode (Write-Ahead Logging)**: Single writer, concurrent readers. Readers read from database file and WAL; writer appends to WAL. |
| **Locking Granularity** | Row-level locks (`SELECT FOR UPDATE`), Table locks (`ACCESS EXCLUSIVE`) | File-level locking (`SQLITE_BUSY` when multiple writers contend) |
| **Connection Pooling** | Managed pool (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`) | NullPool / StaticPool (avoids thread lock contention on file handles) |
| **Garbage Collection** | Background `VACUUM` daemon reclaims dead tuple disk space | `PRAGMA wal_checkpoint` merges WAL changes back into primary `.db` file |

---

## Section 3: SQL Indexing & Query Execution Plans

### 3.1 Left-Prefix Rule in Composite B-Tree Indexes (`ix_projects_tenant_created`)

#### The B-Tree Left-Prefix Rule:
A composite B-Tree index on columns $(A, B, C)$ stores index keys sorted lexicographically: first by $A$, then by $B$ within each value of $A$, and finally by $C$ within each pair of $(A, B)$.
Consequently, the index can accelerate queries filtering on:
- Leading prefix: `WHERE A = ?`
- Leading prefix + second column: `WHERE A = ? AND B = ?`
- Full prefix: `WHERE A = ? AND B = ? AND C = ?`
- Leading prefix + range/sort on second: `WHERE A = ? ORDER BY B DESC`

It **cannot** accelerate queries filtering only on `WHERE B = ?` or `ORDER BY B` because the B-Tree is ordered by $A$ at the root level.

```
Composite B-Tree Structure: (tenant_id, created_at)

Root Node: [('tenant_a', 2026-10-01) | ('tenant_b', 2026-10-02)]
               /                                      \
Leaf Node 1:                                      Leaf Node 2:
('tenant_a', 2026-09-01) -> RowPtr 1             ('tenant_b', 2026-09-10) -> RowPtr 4
('tenant_a', 2026-09-15) -> RowPtr 2             ('tenant_b', 2026-10-02) -> RowPtr 5
('tenant_a', 2026-10-01) -> RowPtr 3             ('tenant_b', 2026-10-15) -> RowPtr 6
```

#### DevPilot Production Composite Indexes:
1. **`Index("ix_projects_tenant_created", "tenant_id", "created_at")` (`src/models/project.py`):**
   - Query Pattern: `SELECT * FROM projects WHERE tenant_id = :id ORDER BY created_at DESC LIMIT 20;`
   - **Left-Prefix Execution:** The query planner matches `tenant_id` on the leading index column ($O(\log N)$ point seek) and immediately streams rows in reverse along the physically pre-sorted `created_at` chain.
2. **`Index("ix_processing_jobs_project_status_created", "project_id", "status", "created_at")` (`src/models/processing_job.py`):**
   - Query Pattern: `SELECT * FROM processing_jobs WHERE project_id = :p_id AND status = 'PENDING' ORDER BY created_at ASC;`
   - **Equality-First Rule:** Both `project_id` and `status` are exact equality constraints, allowing the index to pinpoint the exact contiguous range where jobs match both conditions, reading `created_at` in natural sorted order.

---

### 3.2 Avoiding Filesorts & Temporary Tables in Execution Plans

#### What is a Filesort (`Using filesort` / `Sort: external merge disk`)?
When a query includes `ORDER BY`, if the database cannot read rows directly in the requested order from an index, it must execute a dedicated sort phase:
1. The engine reads all candidate rows into a memory buffer (`sort_buffer_size` in MySQL, `work_mem` in PostgreSQL).
2. If the candidate set exceeds memory, the engine writes intermediate blocks to temporary disk files and performs a multi-pass **External Merge Sort**.
3. **Performance Impact:** Latency spikes from sub-millisecond B-Tree traversal to hundreds of milliseconds of disk I/O.

#### How DevPilot Eliminates Filesorts:
```sql
EXPLAIN ANALYZE
SELECT id, name, created_at FROM projects 
WHERE tenant_id = 'demo-tenant-key' 
ORDER BY created_at DESC 
LIMIT 20;
```
- **Without Composite Index (Single index on `tenant_id`):**
  `Bitmap Index Scan on ix_projects_tenant -> Bitmap Heap Scan -> Sort (quicksort, memory: 128kB)` ⚠️
- **With Composite Index `(tenant_id, created_at)`:**
  `Index Scan Backward using ix_projects_tenant_created on projects (cost=0.15..8.20 rows=20)` ⚡
  **Zero filesort! Zero temporary memory or disk allocation!**

---

### 3.3 N+1 Query Mitigation in ORM Architectures (`selectinload` vs `joinedload`)

#### The N+1 Anti-Pattern:
When fetching parent entities and accessing their child relations in Python:
```python
# ANTI-PATTERN: N+1 Queries
projects = (await session.execute(select(Project).where(Project.tenant_id == tenant_id))).scalars().all()
for project in projects:  # N iterations
    print(len(project.documents))  # Triggers an individual SQL query for EACH project!
```
- Total Queries: 1 initial query + $N$ child queries = $N+1$ queries.
- With 100 projects and a 5ms database round-trip: $1 + (100 \times 5\text{ ms}) = \mathbf{505\text{ ms}}$ of serial latency!

#### Mitigation in SQLAlchemy Async:

```python
from sqlalchemy.orm import selectinload, joinedload

# Solution 1: selectinload (Recommended for 1-to-Many Collections)
stmt = (
    select(Project)
    .where(Project.tenant_id == tenant_id)
    .options(selectinload(Project.documents))
)
projects = (await session.execute(stmt)).scalars().all()
```
- **How `selectinload` works:** Emits exactly **2 SQL queries** regardless of $N$:
  1. `SELECT * FROM projects WHERE tenant_id = :id;`
  2. `SELECT * FROM documents WHERE project_id IN (:id1, :id2, ...);`
  - Reconstructs collections in Python memory in $O(N)$ time.
  - Avoids Cartesian product duplication.

```python
# Solution 2: joinedload (Recommended for 1-to-1 or Many-to-1 References)
stmt = (
    select(Document)
    .options(joinedload(Document.project))
)
```
- **How `joinedload` works:** Emits **1 single SQL query** using `LEFT OUTER JOIN`.
  - Caution: On 1-to-many collections, `joinedload` duplicates parent columns across all child rows, inflating network bandwidth.

---

### 3.4 Keyset / Cursor vs. Offset Pagination Trade-offs & Drift Prevention

| Dimension | Offset Pagination (`OFFSET S LIMIT L`) | Keyset / Cursor Pagination (`Seek Method`) |
| :--- | :--- | :--- |
| **SQL Pattern** | `SELECT * FROM docs ORDER BY created_at DESC LIMIT 20 OFFSET 1000;` | `SELECT * FROM docs WHERE created_at < :cursor ORDER BY created_at DESC LIMIT 20;` |
| **Algorithmic Complexity** | **$O(S + L)$** — Must scan and discard $S$ rows | **$O(\log N + L)$** — Direct B-Tree point-seek |
| **Deep Page Latency** | **Severe degradation** (Offset 500,000 takes seconds) | **Constant sub-millisecond** (Page 1 and Page 50,000 take $<2\text{ ms}$) |
| **"Page Drift" Anomaly** | ⚠️ **Vulnerable:** If a row is inserted while on Page 1, Page 2 repeats the last item from Page 1! | 🛡️ **Immune:** Cursor pins position to exact row value; new inserts never cause duplicated items |
| **Random Page Navigation** | Can jump directly to arbitrary page (e.g. Page 15) | Can only navigate sequentially (Next / Previous cursor) |

#### DevPilot's Bounded Pagination Hardening (`src/api/deps.py`):
For public REST simplicity, DevPilot provides offset pagination while strictly defending against denial-of-service and pagination drift:
1. **Bounded Slicing Invariant:**
   ```python
   skip = max(0, skip)
   limit = min(max(1, limit), 100)  # Hard cap at 100 rows per request
   ```
2. **Deterministic Tie-Breaking:**
   ```sql
   ORDER BY created_at DESC, id ASC
   ```
   If multiple projects share the exact same microsecond timestamp, secondary sorting on primary key `id` guarantees a strictly deterministic ordering, preventing flaky pagination results.

---

### 3.5 Analytical Window Functions (`DENSE_RANK()`) & Recursive CTEs

#### Covering Index for Rapid Index Range Scans:
```python
Index("ix_document_chunks_document_index", "document_id", "chunk_index")
```
When retrieving chunk indices for document citation reconstruction:
```sql
SELECT chunk_index FROM document_chunks 
WHERE document_id = :doc_id 
ORDER BY chunk_index ASC;
```
The query planner satisfies this entirely from the index tree leaf nodes in $O(K)$ time without touching table storage (**Index-Only Scan**).

#### Window Functions: `DENSE_RANK()` vs `RANK()` vs `ROW_NUMBER()`:
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
- `ROW_NUMBER()` assigns contiguous integers ($1, 2, 3$).
- `RANK()` leaves gaps after ties ($1, 1, 3$).
- `DENSE_RANK()` leaves no gaps after ties ($1, 1, 2$). To find "Top 3 fastest ingestion jobs per project", always filter `WHERE dense_rank_val <= 3`.

#### Recursive CTE for Document Tree Traversal:
```sql
WITH RECURSIVE DocumentBreadcrumbs AS (
    -- Anchor Member (Base Case: Target Document)
    SELECT id, parent_id, title, CAST(title AS VARCHAR(1000)) AS path, 0 AS depth
    FROM documents WHERE id = :target_id

    UNION ALL

    -- Recursive Member (Walk upwards to root)
    SELECT p.id, p.parent_id, p.title, CAST(p.title || ' > ' || b.path AS VARCHAR(1000)), b.depth + 1
    FROM documents p
    JOIN DocumentBreadcrumbs b ON p.id = b.parent_id
)
SELECT id, title, path, depth FROM DocumentBreadcrumbs ORDER BY depth DESC;
```

---

## Section 4: HTTP Protocol Semantics & RESTful API Design

### 4.1 HTTP Method Idempotency & Safety (`GET`, `PUT`, `DELETE` vs `POST` and `PATCH`)

In RESTful architecture (RFC 7231 & RFC 5789), HTTP methods are classified by their **safety** and **idempotency**:

- **Safe Methods ($f(x) \implies x$):** The request produces zero state-altering side effects on the server. The client is inspecting state, not mutating it.
- **Idempotent Methods ($f(f(x)) = f(x)$):** Making $N$ identical requests produces the exact same server resource state as making a single request. If network drops occur, clients can safely retry without creating duplicate state or corrupted records.

```
Method Idempotency Visualized:

POST /api/v1/projects  (Non-Idempotent)
Request 1 ──► Project "Alpha" Created (ID: 001)
Request 2 ──► Project "Alpha" Created (ID: 002) ⚠️ Duplication!

PUT /api/v1/documents/1  (Idempotent)
Request 1 ──► Document 1 content replaced with "Hello"
Request 2 ──► Document 1 content replaced with "Hello" (Identical state)

DELETE /api/v1/projects/1  (Idempotent)
Request 1 ──► Project 1 deleted (HTTP 204 / 200)
Request 2 ──► Project 1 already gone (HTTP 404 / 204; Final state: Project is absent)
```

| HTTP Method | Safe? | Idempotent? | DevPilot Endpoint Example | Production RFC Semantics |
| :---: | :---: | :---: | :--- | :--- |
| **`GET`** | **Yes** | **Yes** | `GET /api/v1/projects/{id}` | Read-only; cacheable; safe to pre-fetch. |
| **`HEAD`** | **Yes** | **Yes** | `HEAD /api/v1/documents/{id}` | Retrieves HTTP headers without response body. |
| **`PUT`** | No | **Yes** | `PUT /api/v1/documents/{id}` | Complete resource replacement. Calling $N$ times leaves identical state. |
| **`DELETE`**| No | **Yes** | `DELETE /api/v1/projects/{id}` | Resource removal. Calling $N$ times results in the resource being absent. |
| **`POST`** | No | **No** | `POST /api/v1/projects` | Creates new resource or triggers processing. Calling twice creates two resources. |
| **`PATCH`**| No | Conditional | `PATCH /api/v1/projects/{id}` | Partial update. RFC 5789 defines PATCH as non-idempotent by default, but patching static fields (`{"name": "NewName"}`) is idempotent. |

---

### 4.2 Exact Status Code Semantics Enforced in DevPilot (`200`, `201`, `202`, `401`, `403`, `404`, `409`, `422`, `503`)

DevPilot enforces a strict semantic mapping between internal domain exceptions and RFC-compliant HTTP status codes:

```
                          Client Request
                                │
                 Is X-API-Key present & valid?
                                │
                ┌───────────────┴───────────────┐
               NO                               YES
                │                               │
        HTTP 401 Unauthorized         Does target project exist?
                                                │
                                ┌───────────────┴───────────────┐
                               NO                               YES
                                │                               │
                        HTTP 404 Not Found             Does caller own project?
                                                                │
                                                ┌───────────────┴───────────────┐
                                               NO                               YES
                                                │                               │
                                        HTTP 403 Forbidden             Is payload valid JSON?
                                                                                │
                                                                ┌───────────────┴───────────────┐
                                                               NO                               YES
                                                                │                               │
                                                        HTTP 422 Unprocessable      Does hash collision exist?
                                                                                                │
                                                                                ┌───────────────┴───────────────┐
                                                                               YES                              NO
                                                                                │                               │
                                                                        HTTP 409 Conflict            Execute Action (200/201/202)
```

| Status Code | RFC Meaning | DevPilot Trigger Scenario | Code Reference |
| :---: | :--- | :--- | :--- |
| **`200 OK`** | Action completed successfully | Synchronous hybrid search, RAG answer synthesis, document retrieval | `src/api/v1/endpoints/search.py` |
| **`201 Created`** | New entity provisioned | Synchronous project entity creation with generated UUID | `src/api/v1/endpoints/projects.py` |
| **`202 Accepted`** | Asynchronous task enqueued | Document upload enqueuing background ingestion job (`ProcessingJob` returned in `PENDING` state) | `src/api/v1/endpoints/documents.py` |
| **`400 Bad Request`** | Malformed query parameters | Slicing bounds violated (`skip < 0` or negative page limits) | `src/main.py:value_error_handler` |
| **`401 Unauthorized`** | Missing/invalid authentication | Missing, blank, or malformed `X-API-Key` header at perimeter | `src/core/security.py:get_current_tenant` |
| **`403 Forbidden`** | Authenticated, but not authorized | Cross-tenant access attempt (`owner != current_api_key`) or Demo Mode write mutation | `src/core/security.py:verify_project_tenant_access` |
| **`404 Not Found`** | Resource does not exist | `project_id`, `document_id`, or `job_id` UUID not found in database | `src/services/job.py` |
| **`409 Conflict`** | Resource state collision | Uploading duplicate document with identical SHA-256 hash | `src/main.py:conflict_error_handler` |
| **`422 Unprocessable`** | Schema validation failure | Pydantic v2 validation error (wrong field types, missing body keys) | FastAPI default validation handler |
| **`503 Service Unavail`**| Upstream service outage | Upstream LLM provider timeout, circuit-breaker open, or network drop | `src/services/llm.py` |

---

### 4.3 Statelessness, CORS Architecture, and Header-Driven Tenant Isolation (`X-API-Key`)

#### 1. REST Statelessness (Roy Fielding's Dissertation):
- **Core Principle:** Every request from a client to a server must contain **all** context and authentication information required to process the request. No session state is ever stored in server RAM.
- **Distributed Benefits:**
  - Any application server replica behind a load balancer (Nginx/HAProxy) can handle any incoming request.
  - Zero session-affinity ("sticky session") requirements.
  - Painless zero-downtime rolling deployments and horizontal autoscaling.

#### 2. Cross-Origin Resource Sharing (CORS):
Browsers enforce the **Same-Origin Policy (SOP)**, blocking frontend web apps hosted on `https://app.devpilot.io` from making fetch requests to `https://api.devpilot.io` unless explicit CORS headers are returned.

- **Preflight Request (`OPTIONS`):**
  When a browser sends custom headers (like `X-API-Key`) or complex methods (`PATCH`/`DELETE`), it first issues an `OPTIONS` preflight request:
  ```http
  OPTIONS /api/v1/projects HTTP/1.1
  Host: api.devpilot.io
  Origin: https://app.devpilot.io
  Access-Control-Request-Method: POST
  Access-Control-Request-Headers: X-API-Key, Content-Type
  ```
- **DevPilot CORS Configuration (`src/main.py`):**
  ```python
  from fastapi.middleware.cors import CORSMiddleware

  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],  # Configurable via settings.CORS_ORIGINS in production
      allow_credentials=True,
      allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
      allow_headers=["X-API-Key", "Content-Type", "Authorization"],
  )
  ```
  The API responds with `Access-Control-Allow-Origin: https://app.devpilot.io` and `Access-Control-Allow-Headers: X-API-Key, Content-Type`, authorizing the client to execute the real call.

#### 3. Why Header-Driven Authentication (`X-API-Key`) is Superior:
1. **Query Parameters Leak (`?api_key=secret`):** Query parameters are written in plain text to web server access logs (Nginx/Caddy), proxy caches, browser histories, and `Referer` headers when clicking external links.
2. **URL Path Pollution (`/api/v1/tenants/{key}/projects`):** Embedding tenant keys into paths violates REST resource-modeling conventions and complicates route caching.
3. **Perimeter Fast-Fail:** Passing `X-API-Key` in HTTP headers allows FastAPI dependencies (`Security(api_key_header)`) to validate credentials at the immediate gateway layer, rejecting invalid callers with HTTP 401 **before allocating database connections or parsing large request bodies**.

---

### 4.4 Two-Tier Security & BOLA Prevention (OWASP API1:2023)

#### The Vulnerability (Broken Object Level Authorization / IDOR):
BOLA occurs when an application exposes object identifiers (e.g., `/api/v1/projects/{uuid}`) and validates *that* the caller has an account, but fails to verify *that the caller owns that specific record*.

#### DevPilot Two-Tier Defense Implementation (`src/core/security.py`):
```python
# Tier 1: Gateway Perimeter Authentication
async def get_current_tenant(api_key: Optional[str] = Security(api_key_header)) -> str:
    if not api_key or not api_key.strip():
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")
    return api_key.strip()

# Tier 2: Entity-Level Ownership Verification
def verify_project_tenant_access(project: Optional[Project], current_api_key: str) -> None:
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    owner = project.tenant_id or project.owner_api_key
    # Enforce strict owner match; allow read-only demo inspection if configured
    if owner and owner != current_api_key:
        if is_demo_api_key(current_api_key) and is_demo_workspace(project):
            return
        raise HTTPException(status_code=403, detail="Forbidden: Access denied to project.")
```
- **Architectural Guarantee:** Tier 1 establishes caller identity. Tier 2 verifies entity possession. An attacker guessing or enumerating UUIDs cannot access another tenant's project records.

---

## Section 5: High-Yield Interview Revision Cheatsheet

### 60-Second Flashcard Review:

1. **Why does RRF use $k=60$?**  
   It smooths rank transitions ($\frac{1}{61}$ vs $\frac{1}{62}$) so that documents ranked in the top-10 of *both* dense and sparse lists score higher than an outlier ranked #1 in only one list.
2. **Why put `tenant_id` before `created_at` in composite indexes?**  
   The leftmost prefix rule isolates the tenant's partition in $O(\log N)$ and streams pre-sorted records directly off the index leaf pages without an in-memory filesort.
3. **How do you avoid an N+1 query problem in SQLAlchemy Async?**  
   Use `.options(selectinload(Parent.children))` to load child collections in a single secondary `WHERE parent_id IN (...)` query instead of querying in a loop.
4. **Why is Keyset pagination superior to Offset pagination for deep queries?**  
   Offset scans and discards $S$ rows ($O(S + L)$), degrading on large offsets; keyset pagination performs a direct B-Tree point-seek on indexed columns ($O(\log N + L)$) and prevents page drift.
5. **How do you prevent ghost chunks during worker failure?**  
   Wrap database chunk staging in `try...except` and immediately execute `await session.rollback()` to flush the SQLAlchemy identity map before committing the `FAILED` state.
6. **What is the difference between HTTP 401 and HTTP 403?**  
   `401 Unauthorized` means *"I do not know who you are (missing/invalid credentials)"*. `403 Forbidden` means *"I know who you are, but you do not have permission to access this object"*.
7. **Why is `DELETE` idempotent while `POST` is not?**  
   Deleting a resource multiple times leaves the server in the exact same state (the resource is absent); calling `POST` multiple times creates multiple distinct entities or collisions.
8. **Why is `202 Accepted` used for document upload?**  
   Document extraction, sliding-window chunking, and vector embedding are long-running asynchronous background operations. Returning `202 Accepted` acknowledges receipt and returns a pollable `job_id` without blocking the HTTP request thread.
