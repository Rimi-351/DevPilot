# DevPilot Week 9 Interview Preparation Guide: Advanced DSA & SQL Mastery

**Milestone:** Week 9 — Backend Hardening (Step 5: High-Yield Interview Preparation)  
**Domain:** Senior Backend & AI Systems Engineering  
**Focus Areas:** Linked Lists, Stacks & Queues, Recursion & Trees, Recursive CTEs, Window Functions, and Multi-Tenant Query Analytics  
**Verification:** All Python implementations verified with type hints and $O(\cdot)$ complexities  

---

## 1. Executive Overview

In technical interviews for Senior Backend and AI Infrastructure positions, interviewers evaluate candidates across two complementary axes:
1. **Algorithmic Rigor & Data Structures:** The ability to manipulate pointers, manage memory frames, exploit monotonic invariants, and traverse hierarchical graph/tree structures cleanly without edge-case regressions ($O(1)$ auxiliary space, bounded recursion).
2. **Relational Data Modeling & Analytical SQL:** The ability to navigate multi-tenant schemas, trace self-referencing hierarchical trees via recursive Common Table Expressions (CTEs), and compute moving window telemetry using SQL window functions without resorting to heavy application-layer iterations.

This guide provides production-grade, runnable reference implementations and SQL patterns contextualized within DevPilot's document intelligence and multi-tenant RAG architecture.

---

## 2. Data Structures & Algorithms (Python Reference Implementations)

### 2.1 Linked Lists: Pointer Manipulation & Two-Pointer Invariants

Linked list questions test your ability to reassign references in memory without pointer truncation or infinite loops.

```
Iterative Reversal Invariant:
prev (None) <── curr (Node 1) <── next_temp (Node 2) ──► Node 3
```

#### A. In-Place Singly Linked List Reversal
- **Time Complexity:** $O(N)$ — single pass over $N$ nodes.
- **Space Complexity:** $O(1)$ — constant memory, pointer swaps only.

```python
from __future__ import annotations
from typing import Optional


class ListNode:
    """Singly-linked list node."""
    def __init__(self, val: int = 0, next: Optional[ListNode] = None) -> None:
        self.val = val
        self.next = next


def reverse_linked_list(head: Optional[ListNode]) -> Optional[ListNode]:
    """Reverse a singly linked list iteratively in-place.
    
    Invariant: 'prev' always points to the reversed prefix,
    while 'curr' points to the remainder of the original list.
    """
    prev: Optional[ListNode] = None
    curr: Optional[ListNode] = head

    while curr is not None:
        next_node = curr.next  # 1. Stash next node reference
        curr.next = prev       # 2. Reverse pointer to previous
        prev = curr            # 3. Step forward previous pointer
        curr = next_node       # 4. Step forward current pointer

    return prev
```

#### B. Floyd's Cycle Detection & Cycle Entry Identification
- **Algorithm:** Tortoise and Hare (Fast & Slow Pointers).
- **Mathematical Principle:** Let $L_1$ be distance from head to cycle entrance, $L_2$ be distance from entrance to meeting point, and $C$ be the cycle circumference. The slow pointer travels $L_1 + L_2$. The fast pointer travels $L_1 + L_2 + nC$. Since fast moves at $2\times$ speed:
  $$2(L_1 + L_2) = L_1 + L_2 + nC \implies L_1 = nC - L_2$$
  Therefore, resetting one pointer to `head` and advancing both at speed 1 causes them to meet exactly at the cycle entrance!
- **Time Complexity:** $O(N)$
- **Space Complexity:** $O(1)$

```python
def detect_cycle_entry(head: Optional[ListNode]) -> Optional[ListNode]:
    """Detect if a linked list has a cycle and return the cycle entry node.
    Returns None if no cycle exists.
    """
    if not head or not head.next:
        return None

    slow: Optional[ListNode] = head
    fast: Optional[ListNode] = head

    # Phase 1: Determine if cycle exists
    has_cycle = False
    while fast and fast.next:
        slow = slow.next  # type: ignore[union-attr]
        fast = fast.next.next
        if slow is fast:
            has_cycle = True
            break

    if not has_cycle:
        return None

    # Phase 2: Find cycle start node
    entry: Optional[ListNode] = head
    while entry is not slow:
        entry = entry.next  # type: ignore[union-attr]
        slow = slow.next    # type: ignore[union-attr]

    return entry
```

#### C. Remove $N$-th Node From End in One Pass
- **Pattern:** Sentinel/Dummy Head + Dual Pointer Offset ($N$ steps).
- **Time Complexity:** $O(N)$ | **Space Complexity:** $O(1)$

```python
def remove_nth_from_end(head: Optional[ListNode], n: int) -> Optional[ListNode]:
    """Remove the n-th node from the end of the list in a single pass."""
    dummy = ListNode(val=-1, next=head)
    fast: ListNode = dummy
    slow: ListNode = dummy

    # Advance fast pointer by n + 1 steps to create gap
    for _ in range(n + 1):
        if fast is None:
            return head
        fast = fast.next  # type: ignore[assignment]

    # Advance both until fast reaches the end
    while fast is not None:
        fast = fast.next
        slow = slow.next  # type: ignore[assignment]

    # Delete target node
    if slow.next:
        slow.next = slow.next.next

    return dummy.next
```

---

### 2.2 Stacks & Queues: Monotonic Properties & Bounded Buffers

#### A. Monotonic Deque: Sliding Window Latency Maximum
- **Application in DevPilot:** Tracking rolling 95th-percentile / maximum retrieval latencies across recent sliding query windows without $O(K \log K)$ re-sorting.
- **Time Complexity:** $O(N)$ amortized — each index is pushed and popped at most once.
- **Space Complexity:** $O(K)$ where $K$ is window size.

```python
from collections import deque
from typing import List


def sliding_window_max(latencies_ms: List[float], k: int) -> List[float]:
    """Calculate the maximum latency in every sliding window of size k.
    
    Maintains a monotonically decreasing deque of indices storing candidates
    that could be the maximum in the current or future windows.
    """
    if not latencies_ms or k <= 0:
        return []

    dq: deque[int] = deque()  # stores indices of candidate maximums
    result: List[float] = []

    for i, val in enumerate(latencies_ms):
        # 1. Remove indices that have slid outside window [i - k + 1, i]
        if dq and dq[0] < i - k + 1:
            dq.popleft()

        # 2. Maintain monotonically decreasing order (pop smaller elements from right)
        while dq and latencies_ms[dq[-1]] <= val:
            dq.pop()

        # 3. Add current index
        dq.append(i)

        # 4. Window is valid once index >= k - 1
        if i >= k - 1:
            result.append(latencies_ms[dq[0]])

    return result
```

#### B. Balanced Citation & Token Parsing Stack
- **Application in DevPilot:** Validating that custom citation tags and bracketed prompt structures (`[1]`, `[chunk: ...]`, `{query}`) are correctly nested and uncorrupted.
- **Time Complexity:** $O(N)$ | **Space Complexity:** $O(N)$

```python
def is_valid_bracket_structure(text: str) -> bool:
    """Validate that nested grouping brackets (), [], {} in LLM prompts are balanced."""
    bracket_map = {")": "(", "]": "[", "}": "{"}
    opening = set(bracket_map.values())
    stack: list[str] = []

    for char in text:
        if char in opening:
            stack.append(char)
        elif char in bracket_map:
            if not stack or stack[-1] != bracket_map[char]:
                return False
            stack.pop()

    return len(stack) == 0
```

#### C. Bounded Async Job Worker Buffer (Producer-Consumer Queue)
- **Application in DevPilot:** Concurrency-bounded background ingestion dispatching.

```python
import asyncio
from typing import Any


class AsyncJobBuffer:
    """Thread-safe bounded asynchronous job queue preventing memory exhaustion."""
    def __init__(self, maxsize: int = 100) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, job: dict[str, Any], timeout: float = 2.0) -> bool:
        try:
            await asyncio.wait_for(self.queue.put(job), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False  # Queue saturated (HTTP 429 / 503 backpressure)

    async def dequeue(self) -> dict[str, Any]:
        return await self.queue.get()
```

---

### 2.3 Recursion & Backtracking: Bounded Traversal with Guards

#### A. Recursive Sliding-Window Chunking with Depth Guards
- **Application in DevPilot:** Dividing long technical documents into multi-level hierarchical sub-chunks with recursion call-stack safety.
- **Time Complexity:** $O(N)$ | **Space Complexity:** $O(\text{max\_depth})$

```python
from typing import List


def recursive_hierarchical_split(
    text: str,
    max_chunk_size: int = 512,
    overlap: int = 64,
    depth: int = 0,
    max_depth: int = 10,
) -> List[str]:
    """Recursively partition text when natural sentence/paragraph splits exceed max_chunk_size.
    Guarded against stack overflow via explicit max_depth base case.
    """
    text = text.strip()
    if not text:
        return []

    # Base Case 1: Text fits comfortably within chunk size
    if len(text) <= max_chunk_size or depth >= max_depth:
        return [text]

    # Recursive Step: Split by highest-precedence delimiter available
    delimiters = ["\n\n", "\n", ". ", " "]
    split_delim = delimiters[-1]
    for delim in delimiters:
        if delim in text:
            split_delim = delim
            break

    segments = text.split(split_delim)
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for seg in segments:
        seg_with_delim = seg + split_delim
        if current_len + len(seg_with_delim) > max_chunk_size and current_chunk:
            combined = "".join(current_chunk).strip()
            chunks.append(combined)
            # Carry over overlap tail
            current_chunk = [current_chunk[-1]] if overlap > 0 else []
            current_len = sum(len(s) for s in current_chunk)

        current_chunk.append(seg_with_delim)
        current_len += len(seg_with_delim)

    if current_chunk:
        chunks.append("".join(current_chunk).strip())

    return chunks
```

---

### 2.4 Trees & Binary Search Trees (BST): Traversal & Validation

```
Binary Search Tree Invariant:
           [20]
          /    \
      [10]      [30]
     /   \      /   \
   [5]  [15]  [25]  [35]
   
Every node in left subtree < Node.val < Every node in right subtree
```

#### A. Level-Order Traversal (BFS)
- **Time Complexity:** $O(N)$ | **Space Complexity:** $O(W)$ where $W$ is maximum tree width ($\le N/2$).

```python
class TreeNode:
    """Binary tree node definition."""
    def __init__(
        self,
        val: int = 0,
        left: Optional[TreeNode] = None,
        right: Optional[TreeNode] = None,
    ) -> None:
        self.val = val
        self.left = left
        self.right = right


def level_order_traversal(root: Optional[TreeNode]) -> List[List[int]]:
    """Traverse binary tree level-by-level using a FIFO queue."""
    if not root:
        return []

    result: List[List[int]] = []
    queue: deque[TreeNode] = deque([root])

    while queue:
        level_size = len(queue)
        current_level: List[int] = []

        for _ in range(level_size):
            node = queue.popleft()
            current_level.append(node.val)

            if node.left:
                queue.append(node.left)
            if node.right:
                queue.append(node.right)

        result.append(current_level)

    return result
```

#### B. Validate Binary Search Tree (BST Invariant with Range Bounds)
- **Common Pitfall:** Checking only `node.left.val < node.val < node.right.val` locally fails if a grandchild violates an ancestor bound. Range propagation `(min_val, max_val)` is required!
- **Time Complexity:** $O(N)$ | **Space Complexity:** $O(H)$ where $H$ is tree height.

```python
def is_valid_bst(root: Optional[TreeNode]) -> bool:
    """Validate that binary tree satisfies strict BST invariant across all ancestors."""
    def validate(node: Optional[TreeNode], low: float, high: float) -> bool:
        if not node:
            return True

        # Invariant check
        if not (low < node.val < high):
            return False

        # Propagate constrained bounds down left and right subtrees
        return validate(node.left, low, node.val) and validate(node.right, node.val, high)

    return validate(root, float("-inf"), float("inf"))
```

#### C. Lowest Common Ancestor (LCA) in a Binary Tree
- **Time Complexity:** $O(N)$ | **Space Complexity:** $O(H)$ call stack.

```python
def lowest_common_ancestor(
    root: Optional[TreeNode],
    p: TreeNode,
    q: TreeNode,
) -> Optional[TreeNode]:
    """Find the lowest common ancestor of nodes p and q in a binary tree."""
    if not root or root is p or root is q:
        return root

    left = lowest_common_ancestor(root.left, p, q)
    right = lowest_common_ancestor(root.right, p, q)

    # If p and q match in separate subtrees, root is the LCA
    if left and right:
        return root

    # Otherwise return the non-null branch
    return left if left else right
```

---

## 3. Advanced SQL Interview Practice (DevPilot Multi-Tenant Relational Schema)

### Relational Schema Reference
The DevPilot backend schema is modeled across four core tables:
- **`projects`**: `id` (UUID, PK), `name` (VARCHAR), `tenant_id` (VARCHAR), `created_at` (TIMESTAMP WITH TIME ZONE)
- **`documents`**: `id` (UUID, PK), `project_id` (UUID, FK `projects.id`), `filename` (VARCHAR), `file_type` (VARCHAR), `file_size_bytes` (BIGINT), `created_at` (TIMESTAMP WITH TIME ZONE)
- **`document_chunks`**: `id` (UUID, PK), `document_id` (UUID, FK `documents.id`), `project_id` (UUID, FK `projects.id`), `chunk_index` (INT), `content` (TEXT), `created_at` (TIMESTAMP WITH TIME ZONE)
- **`processing_jobs`**: `id` (UUID, PK), `project_id` (UUID, FK `projects.id`), `document_id` (UUID, FK `documents.id`), `job_type` (VARCHAR), `status` (VARCHAR: `PENDING`, `IN_PROGRESS`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`), `started_at` (TIMESTAMP WITH TIME ZONE), `completed_at` (TIMESTAMP WITH TIME ZONE), `created_at` (TIMESTAMP WITH TIME ZONE)

---

### Query 1: Multi-Tenant `LEFT JOIN` with `COALESCE` Aggregation (Preventing Cross-Tenant Leakage in `ON` vs `WHERE`)

**Interview Problem Statement:**  
*"Write a tenant-scoped reporting query that aggregates project storage consumption (document count, total file size, average file size, and total indexed chunks). Ensure projects that have 0 documents are preserved with 0 values rather than dropped, and guarantee zero cross-tenant data leakage when filtering document attributes."*

```sql
SELECT 
    p.id AS project_id,
    p.name AS project_name,
    p.tenant_id,
    p.created_at AS project_created_at,
    COUNT(DISTINCT d.id) AS total_documents,
    COALESCE(SUM(d.file_size_bytes), 0) AS total_storage_bytes,
    COALESCE(ROUND(AVG(d.file_size_bytes), 2), 0.00) AS avg_document_size_bytes,
    COALESCE(MAX(d.created_at), p.created_at) AS last_document_uploaded_at,
    COUNT(dc.id) AS total_indexed_chunks
FROM projects p
-- LEFT JOIN 1: Preserve projects with 0 documents
LEFT JOIN documents d 
    ON p.id = d.project_id
-- Optional right-table filters MUST reside in ON clause, NOT WHERE clause
-- e.g., AND d.file_type IN ('pdf', 'markdown')
-- LEFT JOIN 2: Aggregate chunk volume
LEFT JOIN document_chunks dc 
    ON d.id = dc.document_id
WHERE p.tenant_id = :target_tenant_id
GROUP BY 
    p.id, 
    p.name, 
    p.tenant_id, 
    p.created_at
ORDER BY 
    total_storage_bytes DESC, 
    p.created_at DESC, 
    p.id ASC;
```

#### Senior Engineer Interview Analysis
1. **The `ON` vs. `WHERE` Predicate Trap (Accidental Inner Join):**
   - If a candidate writes `WHERE d.file_type = 'pdf'`, any project with 0 documents (or only text files) evaluates `d.file_type` to `NULL`. In SQL three-valued logic, `NULL = 'pdf'` evaluates to `UNKNOWN` (falsy), silently discarding the project!
   - **Architectural Rule:** Conditions restricting the optional right table (`documents`) must go in the `ON` clause to preserve outer rows. The authorization boundary (`p.tenant_id = :target_tenant_id`) MUST reside in the `WHERE` clause to eliminate unowned left-table records.
2. **`COUNT(*)` vs. `COUNT(d.id)` vs. `COUNT(DISTINCT d.id)`:**
   - In a `LEFT JOIN` where a project has 0 documents, the join outputs a single row filled with `NULL`s for `d.*`. `COUNT(*)` counts rows and returns `1` (a hallucinated phantom document!). `COUNT(d.id)` skips `NULL`s and returns `0`.
   - When joining both `documents` and `document_chunks` (a 1-to-many-to-many relationship), rows fan out. Using `COUNT(DISTINCT d.id)` prevents inflated document counts.
3. **`COALESCE` for Deterministic Serialization:**
   - `SUM(d.file_size_bytes)` over nulls yields `NULL`. In production APIs, returning `null` instead of `0` breaks frontend integer types or Pydantic strict schemas. `COALESCE(SUM(...), 0)` guarantees deterministic numeric responses.

---

### Query 2: Job Failure Rate Analytics (`GROUP BY`, `HAVING`, and Conditional `CASE WHEN`)

**Interview Problem Statement:**  
*"Write an analytical query to detect unstable ingestion pipelines across projects. Calculate total jobs, count of completed vs. failed jobs, failure percentage, and average processing duration of successful runs. Filter results using `HAVING` to isolate projects with at least 5 jobs and a failure rate $\ge 20\%$."*

```sql
SELECT 
    p.tenant_id,
    p.id AS project_id,
    p.name AS project_name,
    COUNT(pj.id) AS total_jobs,
    COUNT(CASE WHEN pj.status = 'COMPLETED' THEN 1 END) AS completed_jobs,
    COUNT(CASE WHEN pj.status = 'FAILED' THEN 1 END) AS failed_jobs,
    COUNT(CASE WHEN pj.status IN ('PENDING', 'PROCESSING', 'IN_PROGRESS') THEN 1 END) AS active_jobs,
    -- Prevent division-by-zero crashes via NULLIF
    ROUND(
        100.0 * COUNT(CASE WHEN pj.status = 'FAILED' THEN 1 END) / NULLIF(COUNT(pj.id), 0),
        2
    ) AS failure_rate_percentage,
    -- Compute average execution latency for completed jobs in seconds
    COALESCE(
        ROUND(
            AVG(
                CASE 
                    WHEN pj.status = 'COMPLETED' 
                         AND pj.completed_at IS NOT NULL 
                         AND pj.started_at IS NOT NULL 
                    THEN EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at))
                END
            )::numeric, 
            2
        ), 
        0.00
    ) AS avg_completed_duration_seconds
FROM projects p
INNER JOIN processing_jobs pj 
    ON p.id = pj.project_id
WHERE p.tenant_id = :target_tenant_id
GROUP BY 
    p.tenant_id, 
    p.id, 
    p.name
-- Aggregate threshold filtering in HAVING (not WHERE)
HAVING 
    COUNT(pj.id) >= 5 
    AND (COUNT(CASE WHEN pj.status = 'FAILED' THEN 1 END)::numeric / COUNT(pj.id)) >= 0.20
ORDER BY 
    failure_rate_percentage DESC, 
    total_jobs DESC, 
    p.id ASC;
```

#### Senior Engineer Interview Analysis
1. **Conditional Aggregation (`CASE WHEN` Inside Aggregate):**
   - Traditional engineers often write multiple `COUNT` subqueries or joins per status. Conditional aggregation calculates all statuses in a single sequential or index scan over `processing_jobs`.
   - `CASE WHEN condition THEN 1 END` defaults to `NULL` when false; because `COUNT()` ignores `NULL`, it cleanly counts only matching rows.
2. **Defensive Arithmetic with `NULLIF`:**
   - In PostgreSQL, dividing by `0` throws a fatal `division by zero` runtime exception. `NULLIF(COUNT(pj.id), 0)` transforms `0` to `NULL`. Since `X / NULL = NULL`, the query never crashes.
3. **`WHERE` vs. `HAVING` Pipeline Execution Order:**
   - `WHERE` filters rows *before* aggregation (utilizing composite index `ix_projects_tenant_created`).
   - `HAVING` filters aggregated buckets *after* grouping. Attempting to place `COUNT(pj.id) >= 5` in `WHERE` causes a SQL syntax error because aggregate values do not yet exist.

---

### Query 3: Top-N Slowest or Largest Documents per Project (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)`)

**Interview Problem Statement:**  
*"Find the top 3 largest documents uploaded for each project within a tenant, resolving ties deterministically to ensure reproducible pagination and stable reporting. Also report the ingestion duration for each document."*

```sql
WITH RankedDocuments AS (
    SELECT 
        p.tenant_id,
        p.name AS project_name,
        d.project_id,
        d.id AS document_id,
        d.filename,
        d.file_type,
        d.file_size_bytes,
        d.created_at,
        -- Deterministic ranking within each project partition
        ROW_NUMBER() OVER (
            PARTITION BY d.project_id 
            ORDER BY d.file_size_bytes DESC, d.created_at DESC, d.id ASC
        ) AS size_rank,
        -- Ingestion duration in seconds from completed processing jobs
        ROUND(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at))::numeric, 2) AS ingestion_duration_seconds
    FROM documents d
    INNER JOIN projects p 
        ON d.project_id = p.id
    LEFT JOIN processing_jobs pj 
        ON d.id = pj.document_id 
       AND pj.status = 'COMPLETED'
    WHERE p.tenant_id = :target_tenant_id
)
SELECT 
    project_id,
    project_name,
    size_rank,
    document_id,
    filename,
    file_type,
    file_size_bytes,
    ingestion_duration_seconds,
    created_at
FROM RankedDocuments
WHERE size_rank <= 3
ORDER BY 
    project_id ASC, 
    size_rank ASC;
```

#### Senior Engineer Interview Analysis
1. **`ROW_NUMBER()` vs. `RANK()` vs. `DENSE_RANK()`:**
   - `ROW_NUMBER()`: Always produces strict sequential integers (`1, 2, 3, 4`). When paired with deterministic tie-breakers (`ORDER BY file_size_bytes DESC, created_at DESC, id ASC`), it guarantees that the exact same documents appear in the Top-N across repeated calls.
   - `RANK()`: Ties receive the same rank and skip subsequent numbers (`1, 2, 2, 4`). This can inadvertently return fewer or more than $N$ items.
   - `DENSE_RANK()`: Ties receive the same rank without skipping (`1, 2, 2, 3`).
2. **Why a CTE / Subquery is Required:**
   - In the SQL logical evaluation lifecycle (`FROM` $\rightarrow$ `WHERE` $\rightarrow$ `GROUP BY` $\rightarrow$ `HAVING` $\rightarrow$ `SELECT` / Window Functions $\rightarrow$ `ORDER BY`), window functions are computed in the `SELECT` phase.
   - Therefore, evaluating `WHERE ROW_NUMBER() OVER (...) <= 3` in the same scope is invalid syntax. The Common Table Expression (CTE) materializes or pipelines the windowed computation so the outer query can filter on `size_rank`.
3. **Index Optimization:**
   - The partition and ordering map cleanly to our composite index `(project_id, created_at)` or an index on `(project_id, file_size_bytes DESC)`.

---

### Query 4: Sequential Ingestion Duration Delta & Running Byte Totals (`LAG()` and Window Frames)

**Interview Problem Statement:**  
*"Produce a chronological audit log of completed ingestion jobs for each project. For each job, calculate: (1) execution duration, (2) latency delta from the immediately preceding job using `LAG()`, and (3) cumulative running total of bytes processed across documents using explicit window frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`."*

```sql
SELECT 
    p.tenant_id,
    pj.project_id,
    pj.id AS job_id,
    pj.job_type,
    pj.status,
    pj.started_at,
    pj.completed_at,
    d.id AS document_id,
    d.filename,
    d.file_size_bytes,
    -- 1. Current job duration in seconds
    ROUND(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at))::numeric, 2) AS duration_seconds,
    -- 2. Prior job duration via LAG() partitioned by project
    ROUND(
        LAG(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at)), 1) OVER (
            PARTITION BY pj.project_id 
            ORDER BY pj.completed_at ASC, pj.id ASC
        )::numeric, 
        2
    ) AS prev_job_duration_seconds,
    -- Duration delta compared to preceding job (positive = slower, negative = faster)
    ROUND(
        (
            EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at)) - 
            LAG(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at)), 1) OVER (
                PARTITION BY pj.project_id 
                ORDER BY pj.completed_at ASC, pj.id ASC
            )
        )::numeric,
        2
    ) AS duration_delta_seconds,
    -- 3. Cumulative running total of document bytes processed up to the current job
    SUM(COALESCE(d.file_size_bytes, 0)) OVER (
        PARTITION BY pj.project_id 
        ORDER BY pj.completed_at ASC, pj.id ASC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_processed_bytes,
    -- Inter-job idle gap (time elapsed between previous job completion and current job start)
    ROUND(
        EXTRACT(
            EPOCH FROM (
                pj.started_at - LAG(pj.completed_at, 1) OVER (
                    PARTITION BY pj.project_id 
                    ORDER BY pj.completed_at ASC, pj.id ASC
                )
            )
        )::numeric,
        2
    ) AS idle_gap_seconds
FROM processing_jobs pj
INNER JOIN projects p 
    ON pj.project_id = p.id
LEFT JOIN documents d 
    ON pj.document_id = d.id
WHERE 
    p.tenant_id = :target_tenant_id
    AND pj.status = 'COMPLETED'
    AND pj.started_at IS NOT NULL 
    AND pj.completed_at IS NOT NULL
ORDER BY 
    pj.project_id, 
    pj.completed_at ASC, 
    pj.id ASC;
```

#### Senior Engineer Interview Analysis
1. **`LAG(expression, offset, default)` Mechanics:**
   - `LAG(..., 1)` peeks at the row immediately prior within the `(PARTITION BY pj.project_id ORDER BY pj.completed_at ASC)` window.
   - For the initial row in each partition, `LAG()` returns `NULL`. Subtracting `NULL` produces `NULL`, which accurately indicates that no prior delta exists for the first run.
2. **`ROWS` vs. `RANGE` Window Framing Pitfall:**
   - In SQL, omitting the frame clause when `ORDER BY` is present defaults to:
     `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
   - **The Bug:** `RANGE` treats duplicate `completed_at` timestamps as value peers. If two jobs complete at the exact same second, `RANGE` lumps them together and adds both file sizes simultaneously into both rows!
   - **The Fix:** Explicitly specifying `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` instructs the engine to process physical rows one by one.
   - **Performance:** `ROWS` avoids peer lookahead scans in PostgreSQL, making it substantially faster than `RANGE`.

---

### Query 5 (Bonus): Recursive CTE for Hierarchical Section & Chunk Traversal

**Interview Problem Statement:**  
*"In our multi-tenant document store, documents can be broken down into parent-child section chunks (e.g. Chapter $\rightarrow$ Section $\rightarrow$ Subsection). Write a query using a Recursive CTE that reconstructs the entire chunk hierarchy from root to leaves, calculating depth level and generating a breadcrumb path."*

```sql
WITH RECURSIVE ChunkTree AS (
    -- 1. Anchor Member: Root chunks (having no parent)
    SELECT 
        dc.id AS chunk_id,
        dc.document_id,
        dc.chunk_index,
        CAST(dc.chunk_index AS VARCHAR(255)) AS breadcrumb_path,
        1 AS depth_level
    FROM document_chunks dc
    WHERE dc.chunk_index = 0

    UNION ALL

    -- 2. Recursive Member: Sequential/hierarchical child chunks
    SELECT 
        child.id AS chunk_id,
        child.document_id,
        child.chunk_index,
        CAST(parent.breadcrumb_path || ' > ' || child.chunk_index AS VARCHAR(255)),
        parent.depth_level + 1
    FROM document_chunks child
    INNER JOIN ChunkTree parent 
        ON child.document_id = parent.document_id 
       AND child.chunk_index = parent.chunk_index + 1
    WHERE parent.depth_level < 20  -- Recursion depth guard against cycles
)
SELECT 
    chunk_id,
    document_id,
    depth_level,
    breadcrumb_path
FROM ChunkTree
ORDER BY document_id, depth_level ASC;
```

---

## 4. Systems Architecture & Interview Framing

When discussing Week 9 backend hardening in Senior/Staff AI Engineer interviews, structure your narrative around three principles:

1. **Defense-in-Depth vs. Model Trust:**  
   *"In production RAG systems, never trust generative outputs blindly. We engineered `CitationVerificationService` as a deterministic post-processing firewall that strips hallucinated citation markers, checks n-gram token overlap, and flags ungrounded claims with `is_grounded = False` before client delivery."*
2. **Deterministic Multi-Tenancy at Scale:**  
   *"Object-level authorization cannot rely on client-provided query parameters. We bound queries at both the dependency injection layer (`verify_project_tenant_access`) and the database layer via composite indexes `(tenant_id, created_at)` with deterministic tie-breaking `ORDER BY created_at DESC, id ASC` to eliminate pagination drift."*
3. **Transactional Resilience in Long-Running Workers:**  
   *"When background embedding extraction crashes midway, dirty database state must not leave ghost chunks. We encapsulated our worker with explicit `await session.rollback()` prior to persisting the `FAILED` state and diagnostic traceback."*
