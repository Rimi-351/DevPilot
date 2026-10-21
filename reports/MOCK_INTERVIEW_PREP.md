# DevPilot Mock Interview & Timed Problem-Solving Master Guide

**Document Version:** 1.0.0  
**Target Roles:** Senior Backend Engineer, Staff AI Systems Engineer, Distributed Infrastructure Architect  
**Domain:** System Design Defense, Behavioral Leadership (STAR), and Advanced Live Coding (DSA & SQL)  

---

## Table of Contents

1. [System Design & Architecture Defense Scripts (The 2-Minute Pitch)](#1-system-design--architecture-defense-scripts-the-2-minute-pitch)
   - [The 2-Minute Senior Backend / AI Platform Pitch](#the-2-minute-senior-backend--ai-platform-pitch)
   - [Architectural Trap Cards & High-Impact Rebuttals](#architectural-trap-cards--high-impact-rebuttals)
2. [Behavioral & Leadership STAR Method Templates](#2-behavioral--leadership-star-method-templates)
   - [Scenario A: Technical Disagreement (Custom RAG Core vs. Heavy Frameworks)](#scenario-a-technical-disagreement-custom-rag-core-vs-heavy-frameworks)
   - [Scenario B: Scaling Under High Stakes (Mitigating Corrupted Multilingual Ingestion)](#scenario-b-scaling-under-high-stakes-mitigating-corrupted-multilingual-ingestion)
   - [Scenario C: Debugging a Critical Production Anomaly (Ghost Chunks & Transaction Boundaries)](#scenario-c-debugging-a-critical-production-anomaly-ghost-chunks--transaction-boundaries)
3. [Timed Coding Problem-Solving: Data Structures & Algorithms](#3-timed-coding-problem-solving-data-structures--algorithms)
   - [DSA Module 1: Trees & Hierarchical Document Parsing (Lowest Common Ancestor)](#dsa-module-1-trees--hierarchical-document-parsing-lowest-common-ancestor)
   - [DSA Module 2: Graphs & Cycle Detection (Graph Valid Tree / Pipeline Verification)](#dsa-module-2-graphs--cycle-detection-graph-valid-tree--pipeline-verification)
   - [DSA Module 3: Topological Sort & DAG Dependency Resolution (Kahn's Algorithm)](#dsa-module-3-topological-sort--dag-dependency-resolution-kahns-algorithm)
   - [DSA Module 4: Binary Search on Answer Space (Capacity to Ship / Ingest within Deadline)](#dsa-module-4-binary-search-on-answer-space-capacity-to-ship--ingest-within-deadline)
4. [Advanced Analytical SQL: Recursive CTEs & Window Functions](#4-advanced-analytical-sql-recursive-ctes--window-functions)
   - [SQL 1: Recursive CTE for Hierarchical Document Tree & Breadcrumb Navigation](#sql-1-recursive-cte-for-hierarchical-document-tree--breadcrumb-navigation)
   - [SQL 2: Multi-Tenant Moving Window Telemetry & Top-K Ingestion Performance](#sql-2-multi-tenant-moving-window-telemetry--top-k-ingestion-performance)
5. [Timed Problem-Solving Execution Checklist](#5-timed-problem-solving-execution-checklist)

---

## 1. System Design & Architecture Defense Scripts (The 2-Minute Pitch)

### The 2-Minute Senior Backend / AI Platform Pitch

> *"If asked: 'Walk me through a complex system you designed and what engineering trade-offs you made.' Deliver this structured pitch in exactly 120 seconds."*

```
[0:00 - 0:25] The Problem & The Trilemma
"I designed and implemented DevPilot, a high-throughput, multi-tenant document intelligence 
and grounded RAG platform. In production AI systems, teams usually hit the 'Precision-Latency-Safety 
Trilemma': dense embeddings miss exact technical keywords like UUIDs or error codes; sparse 
search misses cross-lingual semantics; and LLMs hallucinate citations when context is thin."

[0:25 - 0:55] Architectural Solution (Two-Stage Cascading Pipeline)
"To solve this, I designed a two-stage cascading retrieval architecture:
In Stage 1, an asynchronous FastAPI backend executes dual-path retrieval—dense BGE-small 
vector embeddings via FastEmbed ONNX alongside an in-memory BM25Okapi sparse engine—fused 
via Reciprocal Rank Fusion with constant k=60. This candidate generation step runs in under 
8 milliseconds P50.
For high-precision synthesis, Stage 2 triggers a neural Cross-Encoder that computes deep 
cross-attention over the top 20 candidates, driving our benchmark MRR to a perfect 1.0000."

[0:55 - 1:25] Data Tier, Multi-Tenancy & Fault Isolation
"At the data layer, I built strict multi-tenant isolation via a two-tier model: perimeter 
authentication returns HTTP 401 on missing API keys, while object-level entity checks return 
HTTP 403 on tenant mismatches, eliminating BOLA vulnerabilities. 
Our database schema maintains architectural parity across SQLite and PostgreSQL through 
SQLAlchemy async, backed by composite B-Tree indexes like (tenant_id, created_at) to avoid 
in-memory filesorts. In our background ingestion workers, database transactions enforce strict 
rollback boundaries—if embedding or extraction fails, an immediate rollback wipes the identity 
map, preventing partial 'ghost chunks' from ever leaking into search."

[1:25 - 2:00] Guardrails & Quantitative Impact
"Finally, for reliability, we implemented an Active Output Firewall with a Citation Verification 
Service that computes sentence-to-chunk token overlap to catch ungrounded claims in under 1ms, 
paired with strict negative prompt constraints. 
The system achieves 90% Recall@5 at 8ms latency in standard hybrid mode, 100% precision at 148ms 
in reranked mode, zero ungrounded hallucinations, and is backed by a 90-test automated suite 
running on CI."
```

---

### Architectural Trap Cards & High-Impact Rebuttals

#### Trap 1: *"Why build a custom retrieval pipeline instead of using LangChain or LlamaIndex?"*
- **Rebuttal:** *"Frameworks like LangChain are excellent for prototyping, but they introduce heavy abstraction layers, opaque synchronous blocking calls, dynamic monkey-patching, and high memory footprints that degrade production P99 latency. In DevPilot, we needed explicit control over async event loops, zero-copy ONNX runtime embeddings, in-memory BM25 caches, and fine-grained database transaction rollback boundaries. Building directly on FastAPI and SQLAlchemy gave us a deterministic 8ms P50 latency and zero dependency bloat."*

#### Trap 2: *"BM25 is in-memory. How do you scale this horizontally across 100 worker replicas?"*
- **Rebuttal:** *"In our current single-node and modular topology, in-memory BM25 provides sub-1.5ms lookups with zero network serialization overhead. To scale horizontally across multi-tenant clusters, the architecture is designed to decouple lexical indexing into a distributed search tier (e.g., OpenSearch or Elasticsearch with BM25 scoring plugins) or partition BM25 indexes by `project_id` on disk via memory-mapped inverted files (MMap). Because our retriever interface is abstracted behind an abstract base class, swapping the local BM25 implementation for a clustered cluster client requires changing zero lines of application business logic."*

#### Trap 3: *"What happens if your worker dies while processing a 500-page document?"*
- **Rebuttal:** *"Ingestion is governed by a persistent `ProcessingJob` state machine (`PENDING -> PROCESSING -> COMPLETED | FAILED`). The worker runs in a dedicated async session. If an unhandled exception or crash occurs, `await session.rollback()` clears staged `DocumentChunk` entities from the buffer, preventing ghost chunk pollution. Furthermore, our janitor task queries `ix_processing_jobs_project_status_created` for jobs in `PROCESSING` whose `started_at` timestamp exceeds the 15-minute SLA threshold, automatically transitioning them to `FAILED` with diagnostics and alerting telemetry."*

---

## 2. Behavioral & Leadership STAR Method Templates

### Scenario A: Technical Disagreement (Custom RAG Core vs. Heavy Frameworks)

- **Situation:** During early architecture planning, a peer proposed using an all-in-one framework (LangChain/LlamaIndex) to accelerate initial MVP delivery, whereas I advocated for a native, async-first architecture using FastAPI, SQLAlchemy 2.0, and ONNX Runtime.
- **Task:** Reconcile differing opinions on architectural velocity versus long-term maintainability, latency predictability, and debugging transparency without causing team friction.
- **Action:** 
  1. Rather than debating theoretical merits, I proposed a 1-day time-boxed spike comparing both approaches on three empirical metrics: cold-start memory footprint, P99 request latency under concurrent load, and exception stack trace clarity during network drops.
  2. The spike revealed that the all-in-one framework introduced 80MB of unnecessary transitive dependencies, masked async I/O behind synchronous wrappers, and produced 20-frame deep stack traces on database connection drops.
  3. I presented the findings collaboratively to the team, highlighting that a lean, native implementation required only 200 lines of clean retrieval orchestration while maintaining an 8ms P50 latency.
- **Result:** The team unanimously adopted the native async architecture. The resulting codebase maintained 100% test transparency, achieved sub-10ms response times, and avoided multiple dependency breaking changes in subsequent quarters.

---

### Scenario B: Scaling Under High Stakes (Mitigating Corrupted Multilingual Ingestion)

- **Situation:** 48 hours prior to an executive platform evaluation, stress testing against an edge-case multilingual corpus containing pure emoji strings and non-Latin mathematical symbols triggered unexpected `ZeroDivisionError` crashes and negative slice indexing in the BM25 retrieval service.
- **Task:** Eliminate the defect across both lexical retrieval and neural reranking without degrading query throughput or breaking backward compatibility with existing project chunks.
- **Action:**
  1. Isolated the root cause: documents with only emoji/symbols produced an empty token list (`len(tokens) == 0`), causing BM25 document length calculation (`avgdl`) to divide by zero.
  2. Implemented boundary defenses in `src/services/retrieval/bm25.py` ensuring fallback document lengths (`max(len(tokens), 1)`) and safe handling when document frequencies are zero.
  3. Added explicit short-circuiting in `HybridRetriever` for empty query strings and enforced lower bounds on `top_k` (`max(1, top_k)`).
  4. Authored dedicated regression tests in `tests/test_boundaries.py` covering malformed payloads, zero-length token corpora, and emoji-only documents.
- **Result:** The full test suite returned to 100% pass rate (90/90 tests passing). The platform flawlessly handled adversarial multilingual stress queries during the evaluation without a single 500 error.

---

### Scenario C: Debugging a Critical Production Anomaly (Ghost Chunks & Transaction Boundaries)

- **Situation:** During pipeline stress testing, an audit revealed that several documents marked as `FAILED` (due to upstream PDF parser timeouts) had partial chunks showing up in vector search results.
- **Task:** Identify how partial document fragments bypassed state validation, and re-architect the background ingestion transaction lifecycle to guarantee absolute consistency.
- **Action:**
  1. Traced the execution flow in `src/services/ingestion/pipeline.py` and discovered that `DocumentChunk` entities staged in SQLAlchemy's identity map were being inadvertently flushed when a subsequent error-logging query called `session.commit()` on the same session.
  2. Refactored the ingestion pipeline into an isolated two-phase transactional model: wrapped all chunk extraction, embedding, and insertion in an explicit `try...except` block with an immediate `await session.rollback()`.
  3. Engineered an isolated recovery block that re-fetches the `ProcessingJob` in a clean state, writes the exact failure stack trace into `error_message`, and safely commits the `FAILED` status without flushing dirty chunks.
  4. Added integration tests verifying that failed ingestion attempts leave exactly zero chunk records in the database.
- **Result:** Completely eradicated "ghost chunk" data corruption. Document ingestion achieved ACID compliance, guaranteeing that search indices only expose fully verified, completed documents.

---

## 3. Timed Coding Problem-Solving: Data Structures & Algorithms

In senior backend interviews, coding questions evaluate your ability to select the optimal invariant, write clean type-annotated code, and state exact space/time complexities ($O(\cdot)$).

---

### DSA Module 1: Trees & Hierarchical Document Parsing (Lowest Common Ancestor)

#### Problem Context:
In DevPilot's document parser, documents are represented as a hierarchical tree of sections, subsections, and paragraphs. Given two chunk nodes `p` and `q`, find their Lowest Common Ancestor (LCA) to determine the enclosing parent section for context expansion.

```
                  Root Document (0)
                 /                 \
        Section 1 (1)             Section 2 (2)
       /             \                  \
 Subsection A (3)  Subsection B (4)   Subsection C (5)
```

#### Python Reference Implementation:
```python
from __future__ import annotations
from typing import Optional


class TreeNode:
    """Represents a hierarchical document section or chunk node."""
    def __init__(self, val: int, left: Optional[TreeNode] = None, right: Optional[TreeNode] = None) -> None:
        self.val = val
        self.left = left
        self.right = right


def lowest_common_ancestor(
    root: Optional[TreeNode], 
    p: TreeNode, 
    q: TreeNode
) -> Optional[TreeNode]:
    """Find the Lowest Common Ancestor (LCA) of nodes p and q in a binary tree.
    
    Invariant:
    - If current node is None, return None.
    - If current node is p or q, return current node (found target).
    - Recursively search left and right subtrees.
    - If both left and right return non-None, current node is the LCA split point!
    - Otherwise, propagate the non-None branch.
    
    Time Complexity:  O(N) where N is the number of nodes in the tree.
    Space Complexity: O(H) where H is tree height (call stack depth; O(log N) balanced, O(N) skewed).
    """
    if root is None or root is p or root is q:
        return root

    left = lowest_common_ancestor(root.left, p, q)
    right = lowest_common_ancestor(root.right, p, q)

    if left is not None and right is not None:
        return root  # p and q are in separate subtrees; root is their LCA

    return left if left is not None else right
```

---

### DSA Module 2: Graphs & Cycle Detection (Graph Valid Tree / Pipeline Verification)

#### Problem Context:
DevPilot allows users to define custom asynchronous data processing pipelines consisting of $N$ nodes labeled $0$ to $N-1$ and a list of undirected edges. Verify whether the pipeline forms a **Valid Tree** (connected graph with zero cycles).

#### Mathematical Condition:
A graph of $N$ nodes is a valid tree if and only if:
1. It contains exactly $N - 1$ edges ($E = V - 1$).
2. It is fully connected (a single traversal visits all $N$ nodes without cycles).

#### Python Reference Implementation (Union-Find / Disjoint Set Union):
```python
from __future__ import annotations


class DSU:
    """Disjoint Set Union with Path Compression and Union by Rank."""
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [1] * n
        self.components = n

    def find(self, i: int) -> int:
        if self.parent[i] != i:
            self.parent[i] = self.find(self.parent[i])  # Path compression
        return self.parent[i]

    def union(self, i: int, j: int) -> bool:
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i == root_j:
            return False  # Cycle detected!

        # Union by rank
        if self.rank[root_i] < self.rank[root_j]:
            self.parent[root_i] = root_j
        elif self.rank[root_i] > self.rank[root_j]:
            self.parent[root_j] = root_i
        else:
            self.parent[root_j] = root_i
            self.rank[root_i] += 1

        self.components -= 1
        return True


def is_valid_pipeline_tree(n: int, edges: list[list[int]]) -> bool:
    """Determine if n pipeline stages and undirected edge connections form a valid tree.
    
    Time Complexity:  O(N * alpha(N)) approx O(N) where alpha is the Inverse Ackermann function.
    Space Complexity: O(N) to store parent and rank arrays.
    """
    # Necessary condition: A tree with N nodes must have exactly N - 1 edges
    if len(edges) != n - 1:
        return False

    dsu = DSU(n)
    for u, v in edges:
        if not dsu.union(u, v):
            return False  # Found cycle

    return dsu.components == 1
```

---

### DSA Module 3: Topological Sort & DAG Dependency Resolution (Kahn's Algorithm)

#### Problem Context:
Ingestion jobs have inter-stage dependencies (e.g., OCR extraction must precede chunking, which must precede embedding generation). Given $N$ tasks and prerequisite pairs `[task, prereq]`, find a valid topological order to schedule tasks. If a cycle exists, raise an error.

```
[0: File Ingress] ──► [1: OCR Extract] ──► [2: Chunking] ──► [3: FastEmbed]
                                                  │
                                                  ▼
                                            [4: BM25 Index]
```

#### Python Reference Implementation (Kahn's BFS Algorithm):
```python
from __future__ import annotations
from collections import deque


def schedule_pipeline_tasks(num_tasks: int, prerequisites: list[list[int]]) -> list[int]:
    """Return valid task execution sequence using Kahn's Algorithm (BFS In-Degree).
    
    prerequisites[i] = [a, b] indicates task 'b' must be completed BEFORE task 'a' (b -> a).
    
    Time Complexity:  O(V + E) where V = num_tasks, E = len(prerequisites).
    Space Complexity: O(V + E) for adjacency list and in-degree tracking array.
    """
    adj: list[list[int]] = [[] for _ in range(num_tasks)]
    in_degree = [0] * num_tasks

    for dest, src in prerequisites:
        adj[src].append(dest)
        in_degree[dest] += 1

    # Queue all tasks that have 0 prerequisites (in-degree == 0)
    queue: deque[int] = deque([i for i in range(num_tasks) if in_degree[i] == 0])
    ordered_tasks: list[int] = []

    while queue:
        curr = queue.popleft()
        ordered_tasks.append(curr)

        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered_tasks) != num_tasks:
        # Cycle detected: Not all tasks could be scheduled!
        return []

    return ordered_tasks
```

---

### DSA Module 4: Binary Search on Answer Space (Capacity to Ship / Ingest within Deadline)

#### Problem Context:
DevPilot's background worker has $N$ document batches with page counts `pages = [100, 200, 150, 400, 250]`. Batches must be processed in the given sequential order. You have a deadline of $H$ hours. Each hour, the worker can ingest at most $C$ pages. What is the **minimum hourly processing capacity $C$** required to ingest all documents within $H$ hours?

#### Monotonic Invariant:
If capacity $C$ is sufficient to finish within $H$ hours, any capacity $C' > C$ is also sufficient. If $C$ fails, any $C'' < C$ also fails. This monotonic boolean predicate allows **Binary Search on the Answer Space**:
- $\text{Lower Bound} = \max(\text{pages})$ (must process at least the largest single batch in one hour).
- $\text{Upper Bound} = \sum(\text{pages})$ (processing all pages in 1 hour).

#### Python Reference Implementation:
```python
from __future__ import annotations
import math


def min_ingestion_capacity(pages: list[int], max_hours: int) -> int:
    """Find minimum hourly page ingestion capacity C to finish within max_hours.
    
    Time Complexity:  O(N * log(sum(pages) - max(pages)))
    Space Complexity: O(1) auxiliary space.
    """
    if not pages or max_hours <= 0:
        return 0

    def can_finish(capacity: int) -> bool:
        hours_needed = 0
        for p in pages:
            # Ceiling division without floating-point inaccuracies: (p + capacity - 1) // capacity
            hours_needed += (p + capacity - 1) // capacity
            if hours_needed > max_hours:
                return False
        return hours_needed <= max_hours

    low = max(pages)
    high = sum(pages)
    best_capacity = high

    while low <= high:
        mid = low + (high - low) // 2
        if can_finish(mid):
            best_capacity = mid
            high = mid - 1  # Try finding smaller valid capacity
        else:
            low = mid + 1   # Need more capacity

    return best_capacity
```

---

## 4. Advanced Analytical SQL: Recursive CTEs & Window Functions

### SQL 1: Recursive CTE for Hierarchical Document Tree & Breadcrumb Navigation

#### Problem Statement:
In DevPilot's enterprise workspace, documents are organized in a self-referencing hierarchical folder structure:
`documents(id, parent_id, project_id, title, created_at)`.
Given a target document ID, generate the full folder breadcrumb path from the root down to the document, computing tree depth and total path string.

```sql
WITH RECURSIVE document_hierarchy AS (
    -- Anchor Member: Select the target document
    SELECT 
        d.id,
        d.parent_id,
        d.project_id,
        d.title,
        CAST(d.title AS VARCHAR(1000)) AS breadcrumb_path,
        0 AS depth
    FROM documents d
    WHERE d.id = :target_document_id

    UNION ALL

    -- Recursive Member: Traverse upwards to root parent
    SELECT 
        parent.id,
        parent.parent_id,
        parent.project_id,
        parent.title,
        CAST(parent.title || ' > ' || dh.breadcrumb_path AS VARCHAR(1000)),
        dh.depth + 1
    FROM documents parent
    JOIN document_hierarchy dh ON parent.id = dh.parent_id
)
SELECT 
    id,
    parent_id,
    title,
    breadcrumb_path,
    depth
FROM document_hierarchy
ORDER BY depth DESC;
```

---

### SQL 2: Multi-Tenant Moving Window Telemetry & Top-K Ingestion Performance

#### Problem Statement:
For tenant operational analytics, write a single performant SQL query across `processing_jobs` to compute:
1. The rank of each job within its project ordered by duration (`DENSE_RANK()`).
2. A 3-job moving average of processing duration per project (`AVG(...) OVER ... ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`).
3. Total cumulative chunks processed per project up to each job.

```sql
SELECT 
    pj.project_id,
    pj.id AS job_id,
    pj.status,
    pj.created_at,
    -- Compute duration in seconds
    ROUND(CAST(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at)) AS NUMERIC), 2) AS duration_seconds,
    
    -- Window Function 1: Rank job speed within project
    DENSE_RANK() OVER (
        PARTITION BY pj.project_id 
        ORDER BY EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at)) ASC
    ) AS speed_rank_in_project,

    -- Window Function 2: 3-Job Moving Average Duration (Current + 2 Preceding)
    ROUND(AVG(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at))) OVER (
        PARTITION BY pj.project_id 
        ORDER BY pj.created_at ASC 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )::NUMERIC, 2) AS moving_avg_duration_sec,

    -- Window Function 3: Running cumulative sum of chunks processed
    SUM(COALESCE((pj.result->>'chunks_count')::INTEGER, 0)) OVER (
        PARTITION BY pj.project_id 
        ORDER BY pj.created_at ASC 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_chunks_processed

FROM processing_jobs pj
WHERE pj.status = 'COMPLETED'
  AND pj.created_at >= NOW() - INTERVAL '30 days'
ORDER BY pj.project_id, pj.created_at DESC;
```

---

## 5. Timed Problem-Solving Execution Checklist

*When tackling a live 45-minute coding interview:*

```
[00:00 - 05:00] Clarify & Define Invariants
  ├── Confirm input constraints: N magnitude, negative numbers, empty arrays, edge bounds.
  └── State edge cases out loud: None/null inputs, cycles, disconnected components.

[05:00 - 10:00] Explore Approaches & Agree on Complexity
  ├── Present naive/brute-force approach first (e.g. O(N^2)).
  ├── Propose optimal approach with invariant (e.g. DSU, Kahn's BFS, Binary Search).
  └── Explicitly state target time and space complexities: O(V + E) time, O(V) space.

[10:00 - 30:00] Clean Implementation
  ├── Use standard Python 3.12+ type annotations (list[int], Optional[TreeNode]).
  ├── Write modular, descriptive variable names (in_degree, adj, low, high).
  └── Handle boundary guards immediately at the function entry point.

[30:00 - 40:00] Dry-Run & Test Invariants
  ├── Walk through a concrete small example manually tracing variable states.
  └── Explicitly test edge cases: N = 0, N = 1, single element, cycle graphs.

[40:00 - 45:00] Wrap-Up & Production Tie-In
  └── Connect algorithmic solution back to real-world infrastructure (e.g. DAG scheduling,
      ingestion batching, database partition pruning).
```
