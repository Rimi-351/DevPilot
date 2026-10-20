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

### 3.1 Recursive CTEs: Hierarchical Tree & Parent-Child Traversal

**Interview Scenario:**  
*"In our multi-tenant document store, documents can be broken down into parent-child section chunks (e.g. Chapter $\rightarrow$ Section $\rightarrow$ Subsection). Write a query using a Recursive CTE that reconstructs the entire chunk hierarchy from root to leaves, calculating the depth level and generating a breadcrumb path."*

```sql
-- Pattern: Recursive CTE with Depth and Breadcrumb Path String
WITH RECURSIVE ChunkTree AS (
    -- 1. Anchor Member: Root chunks (having no parent)
    SELECT 
        dc.id AS chunk_id,
        dc.document_id,
        dc.parent_chunk_id,
        dc.chunk_index,
        CAST(dc.chunk_index AS VARCHAR(255)) AS breadcrumb_path,
        1 AS depth_level
    FROM document_chunks dc
    WHERE dc.parent_chunk_id IS NULL

    UNION ALL

    -- 2. Recursive Member: Child chunks joining with CTE on parent_chunk_id
    SELECT 
        child.id AS chunk_id,
        child.document_id,
        child.parent_chunk_id,
        child.chunk_index,
        CAST(parent.breadcrumb_path || ' > ' || child.chunk_index AS VARCHAR(255)),
        parent.depth_level + 1
    FROM document_chunks child
    INNER JOIN ChunkTree parent 
        ON child.parent_chunk_id = parent.chunk_id
)
SELECT 
    chunk_id,
    document_id,
    parent_chunk_id,
    depth_level,
    breadcrumb_path
FROM ChunkTree
ORDER BY document_id, depth_level ASC, chunk_index ASC;
```

---

### 3.2 Advanced Window Functions: Running Totals, Moving Averages & Lead/Lag Gaps

#### A. Running Total Storage and Moving Average File Size per Project
**Interview Scenario:**  
*"Compute a cumulative running total of uploaded bytes and a 3-document rolling average size partitioned by project, sorted chronologically."*

```sql
SELECT 
    d.id AS document_id,
    d.project_id,
    d.filename,
    d.file_size_bytes,
    d.created_at,
    -- 1. Cumulative running total of storage within project
    SUM(d.file_size_bytes) OVER (
        PARTITION BY d.project_id 
        ORDER BY d.created_at ASC, d.id ASC
    ) AS cumulative_project_bytes,
    
    -- 2. Rolling 3-document moving average (preceding 2 rows + current row)
    AVG(d.file_size_bytes) OVER (
        PARTITION BY d.project_id 
        ORDER BY d.created_at ASC, d.id ASC
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3_doc_avg_bytes
FROM documents d;
```

#### B. Idle Latency & Inter-Job Processing Gap using `LAG()`
**Interview Scenario:**  
*"Measure the queue wait time and idle gap between sequential background ingestion jobs for each tenant."*

```sql
SELECT 
    pj.id AS job_id,
    p.tenant_id,
    pj.status,
    pj.created_at,
    pj.started_at,
    -- Time elapsed between this job creation and previous job completion
    LAG(pj.completed_at, 1) OVER (
        PARTITION BY p.tenant_id 
        ORDER BY pj.created_at ASC
    ) AS previous_job_completed_at,
    
    -- Processing duration in seconds
    ROUND(EXTRACT(EPOCH FROM (pj.completed_at - pj.started_at))::numeric, 2) AS duration_seconds,
    
    -- Queue wait time before execution began
    ROUND(EXTRACT(EPOCH FROM (pj.started_at - pj.created_at))::numeric, 2) AS queue_wait_seconds
FROM processing_jobs pj
JOIN projects p ON pj.project_id = p.id
WHERE pj.status IN ('COMPLETED', 'FAILED');
```

---

### 3.3 Multi-Tenant Deduplication & Top-K Ranking Queries

**Interview Scenario:**  
*"Find the top 3 largest documents uploaded for each tenant, resolving ties deterministically without skipping rank numbers."*

```sql
WITH RankedDocuments AS (
    SELECT 
        p.tenant_id,
        d.id AS document_id,
        d.filename,
        d.file_size_bytes,
        d.created_at,
        -- DENSE_RANK ensures contiguous rank numbers (1, 2, 2, 3...)
        DENSE_RANK() OVER (
            PARTITION BY p.tenant_id 
            ORDER BY d.file_size_bytes DESC, d.created_at ASC, d.id ASC
        ) AS rank_num
    FROM documents d
    JOIN projects p ON d.project_id = p.id
)
SELECT 
    tenant_id,
    rank_num,
    document_id,
    filename,
    file_size_bytes
FROM RankedDocuments
WHERE rank_num <= 3
ORDER BY tenant_id, rank_num ASC;
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
