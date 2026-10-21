# DevPilot Mock Interview & Timed Problem-Solving Master Guide

**Document Version:** 1.2.0  
**Target Roles:** Senior Backend Engineer, Staff AI Systems Engineer, Distributed Infrastructure Architect  
**Domain:** System Design Defense, Behavioral Leadership (STAR), and Advanced Live Coding (DSA & SQL)  
**Verification Status:** Verified with 90/90 Pytest Unit/Integration/Boundary Tests & Zero Lint Errors  

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
   - [Problem 1: Trees — Lowest Common Ancestor (Binary Tree & Binary Search Tree)](#problem-1-trees--lowest-common-ancestor-binary-tree--binary-search-tree)
   - [Problem 2: Graphs — Course Schedule I & II (Topological Sort via Kahn's Algorithm)](#problem-2-graphs--course-schedule-i--ii-topological-sort-via-kahns-algorithm)
   - [Problem 3: Binary Search on Answer Space — Koko Eating Bananas](#problem-3-binary-search-on-answer-space--koko-eating-bananas)
   - [Problem 4: Binary Search on Answer Space — Capacity To Ship Packages Within D Days](#problem-4-binary-search-on-answer-space--capacity-to-ship-packages-within-d-days)
4. [Advanced Analytical SQL: Canonical Interview Questions](#4-advanced-analytical-sql-canonical-interview-questions)
   - [SQL 1: Department Top Three Salaries (Dense Rank Partitioning)](#sql-1-department-top-three-salaries-dense-rank-partitioning)
   - [SQL 2: Gap-and-Island Consecutive Sequence Detection (Streak Analysis)](#sql-2-gap-and-island-consecutive-sequence-detection-streak-analysis)
   - [SQL 3: Recursive CTE for Hierarchical Document Tree & Breadcrumb Navigation](#sql-3-recursive-cte-for-hierarchical-document-tree--breadcrumb-navigation)
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

### Problem 1: Trees — Lowest Common Ancestor (Binary Tree & Binary Search Tree)

#### Context:
Given two nodes `p` and `q`, find their lowest common ancestor (LCA) in a tree. Evaluates post-order DFS propagation (Binary Tree) vs. value range partitioning (BST).

```
                  Root (3)
                 /        \
               (5)        (1)
              /   \      /   \
            (6)   (2)  (0)   (8)
                 /   \
               (7)   (4)
LCA(5, 1) = 3
LCA(5, 4) = 5
```

#### Part A: Binary Tree LCA (General Case)
- **Time Complexity:** $O(N)$ — traverses at most $N$ nodes.
- **Space Complexity:** $O(H)$ — recursion stack depth ($H \le N$).

```python
from __future__ import annotations
from typing import Optional


class TreeNode:
    """Standard binary tree node."""
    def __init__(self, val: int = 0, left: Optional[TreeNode] = None, right: Optional[TreeNode] = None) -> None:
        self.val = val
        self.left = left
        self.right = right


def lowest_common_ancestor_bt(
    root: Optional[TreeNode], 
    p: TreeNode, 
    q: TreeNode
) -> Optional[TreeNode]:
    """Find the Lowest Common Ancestor (LCA) in a general Binary Tree.
    
    Invariant:
    - If current node is None or matches p or q, return current node.
    - If p and q reside in opposite subtrees, current node is the LCA split point!
    - If only one subtree returns a non-None node, propagate that node upward.
    """
    if root is None or root is p or root is q:
        return root

    left = lowest_common_ancestor_bt(root.left, p, q)
    right = lowest_common_ancestor_bt(root.right, p, q)

    if left is not None and right is not None:
        return root  # Found split point

    return left if left is not None else right
```

#### Part B: Binary Search Tree LCA (Exploiting BST Invariant)
- **Invariant:** For any node `root`, all nodes in `root.left` have values $< \text{root.val}$, and all nodes in `root.right` have values $> \text{root.val}$.
- **Time Complexity:** $O(H)$ — where $H$ is the tree height ($O(\log N)$ average, $O(N)$ worst-case).
- **Space Complexity:** $O(1)$ auxiliary space when implemented iteratively!

```python
def lowest_common_ancestor_bst(
    root: Optional[TreeNode], 
    p: TreeNode, 
    q: TreeNode
) -> Optional[TreeNode]:
    """Find the LCA in a Binary Search Tree (BST) iteratively in O(1) space."""
    curr = root
    val_p, val_q = p.val, q.val

    while curr is not None:
        # If both p and q are smaller than curr, LCA must be in the left subtree
        if val_p < curr.val and val_q < curr.val:
            curr = curr.left
        # If both p and q are greater than curr, LCA must be in the right subtree
        elif val_p > curr.val and val_q > curr.val:
            curr = curr.right
        else:
            # We found the split point (or curr matches p or q)
            return curr

    return None
```

---

### Problem 2: Graphs — Course Schedule I & II (Topological Sort via Kahn's Algorithm)

#### Context:
There are a total of `num_courses` labeled from `0` to `num_courses - 1`. You are given an array `prerequisites` where `prerequisites[i] = [a, b]` indicates you must take course `b` before `a` ($b \to a$).
- **Course Schedule I:** Return `True` if you can finish all courses, `False` otherwise.
- **Course Schedule II:** Return the valid course ordering. If impossible due to a cycle, return `[]`.

```
Graph: [1, 0], [2, 0], [3, 1], [3, 2]
    0 ──► 1 ──► 3
    └───► 2 ───►┘
Valid Topological Order: [0, 1, 2, 3] or [0, 2, 1, 3]
```

#### Python Reference Implementation (Kahn's BFS In-Degree Algorithm):
- **Time Complexity:** $O(V + E)$ where $V = \text{num\_courses}$, $E = \text{len(prerequisites)}$.
- **Space Complexity:** $O(V + E)$ for adjacency list and in-degree counter.

```python
from __future__ import annotations
from collections import deque


def can_finish_courses(num_courses: int, prerequisites: list[list[int]]) -> bool:
    """Course Schedule I: Determine if all courses can be finished (DAG Cycle Detection)."""
    order = find_course_order(num_courses, prerequisites)
    return len(order) == num_courses


def find_course_order(num_courses: int, prerequisites: list[list[int]]) -> list[int]:
    """Course Schedule II: Return valid topological course order using Kahn's Algorithm.
    
    Returns empty list if a dependency cycle exists.
    """
    adj: list[list[int]] = [[] for _ in range(num_courses)]
    in_degree = [0] * num_courses

    # Build directed graph: b -> a
    for dest, src in prerequisites:
        adj[src].append(dest)
        in_degree[dest] += 1

    # Initialize queue with all courses having 0 prerequisites (in_degree == 0)
    queue: deque[int] = deque([course for course in range(num_courses) if in_degree[course] == 0])
    topological_order: list[int] = []

    while queue:
        curr = queue.popleft()
        topological_order.append(curr)

        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If the topological order contains all courses, no cycle exists
    if len(topological_order) == num_courses:
        return topological_order

    return []  # Cycle detected!
```

---

### Problem 3: Binary Search on Answer Space — Koko Eating Bananas

#### Context (LeetCode 875):
Koko loves to eat bananas. There are $N$ piles of bananas where the $i$-th pile has `piles[i]` bananas. The guards will return in $h$ hours.
Koko can decide her eating speed $k$ (bananas per hour). Each hour, she chooses a pile and eats $k$ bananas. If the pile has less than $k$ bananas, she eats all of them and will not eat any more bananas during that hour.
Return the **minimum integer $k$** such that she can eat all the bananas within $h$ hours.

#### Monotonic Invariant:
Let $f(k)$ be the hours needed to eat all piles at speed $k$:
$$f(k) = \sum_{p \in \text{piles}} \left\lceil \frac{p}{k} \right\rceil = \sum_{p \in \text{piles}} \left\lfloor \frac{p + k - 1}{k} \right\rfloor$$
- As speed $k$ increases, hours needed $f(k)$ monotonically decreases.
- Minimum possible speed: $k = 1$.
- Maximum necessary speed: $k = \max(\text{piles})$ (she can finish each pile in $\le 1$ hour).

#### Python Reference Implementation:
- **Time Complexity:** $O(N \cdot \log(\max(\text{piles})))$ where $N = \text{len(piles)}$.
- **Space Complexity:** $O(1)$ auxiliary space.

```python
from __future__ import annotations


def min_eating_speed(piles: list[int], h: int) -> int:
    """Find minimum integer eating speed k to eat all bananas within h hours.
    
    Time Complexity:  O(N * log(max(piles)))
    Space Complexity: O(1)
    """
    if not piles or h < len(piles):
        return -1  # Impossible if hours < number of piles

    def hours_needed_at_speed(k: int) -> int:
        total_hours = 0
        for p in piles:
            # Ceiling division without floating point inaccuracies
            total_hours += (p + k - 1) // k
            if total_hours > h:
                return total_hours  # Early exit optimization
        return total_hours

    low = 1
    high = max(piles)
    min_valid_speed = high

    while low <= high:
        mid = low + (high - low) // 2
        if hours_needed_at_speed(mid) <= h:
            min_valid_speed = mid  # mid is valid; try finding smaller speed
            high = mid - 1
        else:
            low = mid + 1          # mid is too slow; must increase speed

    return min_valid_speed
```

---

### Problem 4: Binary Search on Answer Space — Capacity To Ship Packages Within D Days

#### Context (LeetCode 1011):
A conveyor belt has packages that must be shipped within `days` days. The weights of the packages are given in order by `weights[i]`. Each day, packages are loaded onto the ship in the given order, and the ship cannot be loaded with more weight than its maximum weight capacity.
Return the **least weight capacity** of the ship that will result in all packages being shipped within `days` days.

#### Monotonic Invariant:
- Minimum possible capacity: $\max(\text{weights})$ (the ship must be able to carry the heaviest individual package).
- Maximum necessary capacity: $\sum(\text{weights})$ (shipping all packages on day 1).
- Monotonicity: If capacity $C$ ships all packages in $\le \text{days}$, any $C' > C$ is also valid.

#### Python Reference Implementation:
- **Time Complexity:** $O(N \cdot \log(\sum(\text{weights}) - \max(\text{weights})))$.
- **Space Complexity:** $O(1)$ auxiliary space.

```python
from __future__ import annotations


def ship_within_days(weights: list[int], days: int) -> int:
    """Find least ship weight capacity to ship all packages within given days.
    
    Time Complexity:  O(N * log(sum(weights) - max(weights)))
    Space Complexity: O(1)
    """
    if not weights or days <= 0:
        return 0

    def can_ship_with_capacity(capacity: int) -> bool:
        days_used = 1
        current_day_load = 0

        for w in weights:
            if current_day_load + w > capacity:
                days_used += 1
                current_day_load = w
                if days_used > days:
                    return False
            else:
                current_day_load += w

        return days_used <= days

    low = max(weights)
    high = sum(weights)
    ans = high

    while low <= high:
        mid = low + (high - low) // 2
        if can_ship_with_capacity(mid):
            ans = mid
            high = mid - 1  # Seek smaller capacity
        else:
            low = mid + 1   # Capacity too small

    return ans
```

---

## 4. Advanced Analytical SQL: Canonical Interview Questions

---

### SQL 1: Department Top Three Salaries (Dense Rank Partitioning)

#### Problem Context (LeetCode 185):
A company's executives are interested in seeing who earns the most money in each department. A high earner in a department is an employee who has a salary in the **top three unique salaries** for that department.
Given schemas:
- `Employee(id, name, salary, departmentId)`
- `Department(id, name)`

Find the employees who are high earners in each of the departments.

#### SQL Solution:
```sql
WITH RankedSalaries AS (
    SELECT 
        d.name AS Department,
        e.name AS Employee,
        e.salary AS Salary,
        DENSE_RANK() OVER (
            PARTITION BY e.departmentId 
            ORDER BY e.salary DESC
        ) AS salary_rank
    FROM Employee e
    JOIN Department d ON e.departmentId = d.id
)
SELECT 
    Department,
    Employee,
    Salary
FROM RankedSalaries
WHERE salary_rank <= 3
ORDER BY Department, Salary DESC;
```

#### Why `DENSE_RANK()` vs `RANK()` vs `ROW_NUMBER()`?
- `ROW_NUMBER()` assigns sequential integers ($1, 2, 3, 4$). If two employees tie for 1st place ($100k, $100k), one gets rank 1 and the other gets rank 2.
- `RANK()` leaves gaps after ties ($1, 1, 3$). If two employees tie for 1st place, the next gets rank 3, missing the 2nd unique salary bracket.
- `DENSE_RANK()` produces contiguous ranks without gaps ($1, 1, 2, 3$). Both ties get rank 1, and the next highest salary is rank 2. This satisfies the requirement: **"top three unique salaries"**.

---

### SQL 2: Gap-and-Island Consecutive Sequence Detection (Streak Analysis)

#### Problem Context:
Given a table of user activity or document ingestion events:
`user_activity(user_id, activity_date)`
Find the start date, end date, and duration of all **consecutive active streaks** (consecutive days of activity) for each user.

#### The "Difference of Row Numbers" Invariant:
If dates are strictly consecutive ($D_1, D_1+1, D_1+2$), and we assign a sequential integer `ROW_NUMBER()` ($1, 2, 3$), then the difference:
$$\text{activity\_date} - \text{ROW\_NUMBER}() \times \text{INTERVAL '1 day'}$$
produces a **constant anchor date** for every date in the same consecutive island!

```
Date         Row_Num    Date - Row_Num (Island Group Anchor)
2026-10-01      1       2026-09-30  <── Island 1
2026-10-02      2       2026-09-30  <── Island 1
2026-10-03      3       2026-09-30  <── Island 1
2026-10-05      4       2026-10-01  <── Island 2 (Gap detected!)
2026-10-06      5       2026-10-01  <── Island 2
```

#### SQL Solution:
```sql
WITH DistinctActivities AS (
    -- Deduplicate same-day multiple events
    SELECT DISTINCT 
        user_id, 
        CAST(activity_date AS DATE) AS act_date
    FROM user_activity
),
NumberedEvents AS (
    SELECT 
        user_id,
        act_date,
        ROW_NUMBER() OVER (
            PARTITION BY user_id 
            ORDER BY act_date ASC
        ) AS rn
    FROM DistinctActivities
),
IslandGroups AS (
    SELECT 
        user_id,
        act_date,
        -- Group identifier: Date minus row number remains constant for consecutive days
        act_date - (rn * INTERVAL '1 day') AS island_id
    FROM NumberedEvents
)
SELECT 
    user_id,
    MIN(act_date) AS streak_start_date,
    MAX(act_date) AS streak_end_date,
    COUNT(*) AS streak_length_days
FROM IslandGroups
GROUP BY user_id, island_id
HAVING COUNT(*) >= 1
ORDER BY user_id, streak_start_date ASC;
```

---

### SQL 3: Recursive CTE for Hierarchical Document Tree & Breadcrumb Navigation

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
