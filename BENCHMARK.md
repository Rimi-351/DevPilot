# DevPilot — Retrieval Quality Benchmark & Parameter Sweep Report

> **Repository:** `Rimi-351/DevPilot`  
> **Milestone:** Week 5 Complete — Advanced Retrieval, Cross-Encoder Reranking & 50-Query Parameter Sweep  
> **Date:** October 2026  
> **Artifact Source:** [`artifacts/benchmark_results.json`](artifacts/benchmark_results.json)  
> **Dataset:** [`benchmarks/gold_standard_50.jsonl`](benchmarks/gold_standard_50.jsonl) (50 diverse technical queries)

---

## Executive Summary

This report presents empirical findings from DevPilot's evaluation harness comparing three retrieval architectures across a **50-query gold standard benchmark**:
1. **Dense Vector Retrieval (`vector_only`)**: FastEmbed `BAAI/bge-small-en-v1.5` cosine similarity over 384-dimensional dense vectors.
2. **Hybrid Retrieval (`hybrid`)**: Dense vector similarity fused with sparse BM25 (`rank-bm25` BM25Okapi) using Reciprocal Rank Fusion (RRF, $k=60$).
3. **Hybrid Search with Cross-Encoder Reranking (`hybrid_rerank`)**: RRF candidate pool re-scored via deep cross-attention using `cross-encoder/ms-marco-MiniLM-L-6-v2`.

### Key Conclusions

- **Cross-Encoder Reranking Delivers Perfect Ranking Accuracy**: `hybrid_rerank` achieves an **MRR of 1.00** across all evaluated queries for both $top\_k=3$ and $top\_k=5$, ensuring the most relevant evidence is positioned at rank 1.
- **Dense Retrieval Offers Sub-10ms Latency**: `vector_only` achieves a P50 retrieval latency of **6.83 ms** and P95 of **10.04 ms**, delivering high throughput suitable for low-latency interactive workflows.
- **Hybrid Fusion Bridges the Lexical Gap**: Sparse BM25 combined with dense vectors via RRF guarantees that exact identifiers, constants, and error codes (`ERR_FILE_TOO_LARGE`, `CHUNK_SIZE`, `X-API-Key`) are captured alongside high-level semantic paraphrases.

---

## Formal Metric Definitions

### 1. Hit@k
Measures whether at least one relevant ground-truth chunk appears within the top-$k$ retrieved candidates:

$$\text{Hit@}k(q) = \begin{cases} 1.0 & \text{if } \text{ground\_truth}(q) \cap \text{retrieved}(q)[:k] \neq \emptyset \\ 0.0 & \text{otherwise} \end{cases}$$

Aggregated over $N$ evaluable queries:

$$\text{Hit@}k = \frac{1}{N} \sum_{i=1}^N \text{Hit@}k(q_i)$$

### 2. Mean Reciprocal Rank (MRR)
Evaluates the positional ranking of the first relevant document. For query $q$, let $\text{rank}_i$ be the 1-based index of the first ground-truth item in the retrieved ranking ($0.0$ if not found):

$$\text{RR}(q) = \begin{cases} \frac{1}{\text{rank}_i} & \text{if relevant chunk is retrieved} \\ 0.0 & \text{otherwise} \end{cases}$$

$$\text{MRR} = \frac{1}{N} \sum_{i=1}^N \text{RR}(q_i)$$

An MRR of $1.00$ means the relevant evidence chunk is ranked at index 1 for every query.

### 3. Latency Percentiles (P50 & P95)
- **P50 (Median Latency)**: The 50th percentile execution time in milliseconds; 50% of operations finish faster than this duration.
- **P95 (Tail Latency)**: The 95th percentile execution time; captures 95% of queries and highlights tail latency introduced by neural models and cross-attention.

### 4. Unsupported Claims Rate
Evaluates factual grounding in the synthesized answer. Each generated claim sentence $S$ is evaluated against retrieved context chunks $C$ using token overlap:

$$\text{overlap\_ratio}(S, C) = \frac{|\text{tokens}(S) \cap \text{tokens}(C)|}{|\text{tokens}(S)|}$$

A sentence $S$ is classified as **unsupported** if:

$$\max_{C} \left(\text{overlap\_ratio}(S, C)\right) < 0.40$$

$$\text{unsupported\_claims\_rate} = \frac{\text{Count}(\text{unsupported claim sentences})}{\text{Total claim sentences}}$$

> **Negative Constraint Guardrail:** Polite refusal responses for out-of-scope queries (*"I do not have enough information in the provided documents to answer this question."*) represent valid grounded rejections and are evaluated with a 0.0% unsupported claims rate.

---

## Empirical Benchmark & Parameter Sweep Results

Evaluation executed across **50 diverse queries** from `benchmarks/gold_standard_50.jsonl` with fixed chunk size of 512 characters and top-$k \in [3, 5]$:

| Retrieval Mode | Chunk Size | Top-K | Hit@k | MRR | P50 Ret (ms) | P95 Ret (ms) | P50 Gen (ms) | P95 Gen (ms) | Unsupported Claims |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`vector_only`** | 512 | 3 | **1.00** | 0.97 | **6.83** | **10.04** | 0.04 | 0.05 | 23.67% |
| **`hybrid`** | 512 | 3 | **1.00** | 0.95 | **7.20** | **9.57** | 0.04 | 0.05 | 24.00% |
| **`hybrid_rerank`** | 512 | 3 | **1.00** | **1.00** | 125.68 | 184.29 | 0.05 | 0.06 | 26.00% |
| **`vector_only`** | 512 | 5 | **1.00** | 0.97 | **7.19** | **9.72** | 0.05 | 0.06 | 28.17% |
| **`hybrid`** | 512 | 5 | **1.00** | 0.95 | **7.28** | **10.40** | 0.04 | 0.06 | 28.33% |
| **`hybrid_rerank`** | 512 | 5 | **1.00** | **1.00** | 143.50 | 173.35 | 0.05 | 0.07 | 29.50% |

---

## Comparative Architectural Analysis

```
                              ┌──────────────────────────────────┐
                              │     User Query & Candidate Pool  │
                              └────────────────┬─────────────────┘
                                               │
                   ┌───────────────────────────┴───────────────────────────┐
                   ▼                                                       ▼
        ┌───────────────────────┐                               ┌───────────────────────┐
        │   Dense Vector Search │                               │   Sparse BM25 Search  │
        │   (FastEmbed BGE-384) │                               │   (rank-bm25, Okapi)  │
        │   P50: ~7 ms          │                               │   Indexed in memory   │
        └──────────┬────────────┘                               └──────────┬────────────┘
                   │                                                       │
                   └───────────────────────────┬───────────────────────────┘
                                               ▼
                               ┌───────────────────────────────┐
                               │   Reciprocal Rank Fusion      │
                               │   RRF (k=60) Candidate Merge  │
                               └───────────────┬───────────────┘
                                               │
                                               ▼
                               ┌───────────────────────────────┐
                               │   Cross-Encoder Reranker      │
                               │   (ms-marco-MiniLM-L-6-v2)    │
                               │   MRR: 1.00, P50: ~125 ms     │
                               └───────────────────────────────┘
```

### 1. Vector Only (`vector_only`)
- **Strengths:** Highly efficient (~7ms P50 latency), excels at conceptual, semantic, and paraphrased queries.
- **Weaknesses:** Vulnerable to exact keyword gaps when queries target verbatim code identifiers, error codes, or rare acronyms.
- **Best For:** High-volume user queries where sub-10ms response times are critical.

### 2. Hybrid Search (`hybrid`)
- **Strengths:** Blends BM25 sparse keyword matching and dense vector similarity through Reciprocal Rank Fusion ($k=60$). Resolves lexical gaps without losing semantic understanding. In-memory BM25 index caching ensures minimal latency penalty (~7.2ms vs ~6.8ms).
- **Weaknesses:** Reciprocal Rank Fusion uses rank sums without re-scoring joint token interactions.
- **Best For:** General enterprise search balancing sub-10ms latency and high identifier precision.

### 3. Hybrid with Cross-Encoder Reranking (`hybrid_rerank`)
- **Strengths:** Joint query-document cross-attention using `cross-encoder/ms-marco-MiniLM-L-6-v2` re-ranks top candidates, achieving **MRR = 1.00**. Includes transparent fallback logging (`RERANKER_FALLBACK_ACTIVE`) and metadata attachment (`reranker_applied`, `reranker_engine`).
- **Weaknesses:** Requires extra compute per query (~125–145ms P50 latency).
- **Best For:** Grounded RAG answer synthesis and high-consequence enterprise retrieval where top-1 precision is essential.

---

## Benchmark Dataset Breakdown (50 Queries)

The dataset ([`benchmarks/gold_standard_50.jsonl`](benchmarks/gold_standard_50.jsonl)) is partitioned into 4 distinct challenge categories:

1. **Exact Keyword Matches & Code Identifiers (15 Queries)**: Verifies exact identifier retrieval (`CHUNK_SIZE`, `CHUNK_OVERLAP`, `X-API-Key`, `reciprocal_rank_fusion`, `BM25Okapi`, `BAAI/bge-small-en-v1.5`, `JobStatus`, `alembic upgrade head`, SHA-256).
2. **Paraphrased & Conceptual Queries (15 Queries)**: Tests semantic generalization without keyword overlap (multi-tenant isolation, sliding-window chunking, cross-encoder concepts, BM25 index caching, citation provenance).
3. **Multi-Chunk Fact Synthesis Queries (10 Queries)**: Requires retrieving and synthesizing facts across multiple distinct chunks (e.g. chunking configuration + embedding vectors; API key authentication + project ownership columns).
4. **Out-of-Scope / Negative Constraint Queries (10 Queries)**: Queries on unanswerable topics (Kubernetes Helm, Kafka streaming, AWS Bedrock, GraphQL Apollo, Redis Sentinel, Stripe webhooks, LoRA PyTorch FSDP) verifying that the system returns `NEGATIVE_RESPONSE` without hallucination.

---

## Reproducing the Benchmark

Execute the parameter sweep across all modes and top-$k \in [3, 5]$:

```bash
# Run complete parameter sweep on 50-query dataset
python -m src.evaluation.runner --dataset benchmarks/gold_standard_50.jsonl --sweep --mock-llm

# Evaluate single mode with custom top_k
python -m src.evaluation.runner --mode hybrid_rerank --top-k 3
```

All results are automatically persisted to [`artifacts/benchmark_results.json`](artifacts/benchmark_results.json).

---

## Week 6: Bounded Agentic Workflow Telemetry & Guardrail Verification

### 1. Overview & Architecture

Week 6 extends DevPilot from direct query-response RAG to a bounded agentic research workflow. The agent operates under a deterministic 4-phase finite state machine (FSM):

$$\text{SEARCH} \longrightarrow \text{INSPECT} \longrightarrow \text{SUMMARIZE} \longrightarrow \text{PROPOSE}$$

Tool execution is isolated behind `GuardedToolDispatcher`, providing runtime validation, phase boundary gating, per-tool timeout isolation, and structured error reflection back to the LLM context.

### 2. End-to-End Workflow Execution Metrics

Telemetry captured across complete FSM execution cycles:

| Metric | Target / Constraint | Measured Benchmark | Notes |
|:---|:---:|:---:|:---|
| **Phase Progression** | Strict 4-Phase Sequence | `["SEARCH", "INSPECT", "SUMMARIZE", "PROPOSE"]` | Deterministic progression; zero phase jumping |
| **Tool Execution Count** | Exactly 3 Tool Calls | 3 calls (`search_project`, `inspect_chunk`, `summarize_text`) | 1 tool per active phase prior to `PROPOSE` synthesis |
| **Nominal FSM Iterations** | $\ge 4$ (3 tools + 1 synthesis) | **4 iterations** (Happy Path) | Completes within budget on valid tool arguments |
| **Nominal Runtime (Offline/Mock)** | $< 1.0\text{ s}$ | **$0.002 - 0.05\text{ s}$** | Sub-50ms local execution overhead |
| **Nominal Runtime (Live LLM)** | $< 10.0\text{ s}$ | **$2.5 - 4.5\text{ s}$** | Dependent on LLM token generation latency |
| **Deliverable Quality** | Validated `AgentProposal` | Title, Executive Summary, Actions ($\ge 1$), Confidence ($0.0 - 1.0$) | Verified against Pydantic schema |

### 3. Guardrail Verification Outcomes

| Guardrail Layer | Failure Mode Tested | Injected Condition | Observed System Behavior | Guardrail Status |
|:---|:---|:---|:---|:---:|
| **Phase Boundary Gate** | Out-of-order tool call | Calling `summarize_text` during `SEARCH` phase | Rejected immediately with `ToolExecutionStatus.PHASE_VIOLATION`. Underlying tool logic never executes. | ✅ VERIFIED |
| **Ingress Validation** | Malformed tool arguments | Query length $< 3$ chars or malformed `chunk_id` | `ToolExecutionStatus.VALIDATION_ERROR` logged. Structured schema error reflected to context; agent self-corrects on next iteration. | ✅ VERIFIED |
| **Timeout Isolation** | Slow / hung upstream tool | Tool coroutine delayed beyond `per_tool_timeout` (0.05s) | `asyncio.wait_for` triggers cancellation; `ToolExecutionStatus.TIMEOUT` returned without blocking the event loop. | ✅ VERIFIED |
| **Fault Boundary** | Database / network exception | Unhandled tool exception raised | `ToolExecutionStatus.EXECUTION_ERROR` recorded; error dictionary returned to context without crashing the workflow loop. | ✅ VERIFIED |
| **Hard Loop Cap** | Infinite loop / repeating failure | Permanent tool failure across all iterations | Agent terminates strictly at iteration 5 with `status = "MAX_ITERATIONS_REACHED"` and `final_proposal = None`. | ✅ VERIFIED |

### 4. Integration Test Suite Verification

- **Agent Test Suite (`tests/test_agent.py`)**: **6/6 passed** (0.60s)
- **Full Platform Test Suite (`pytest -v`)**: **61/61 passed** (100% green)
- **Syntax / Linter Verification**: `ruff check src/ tests/ --select E9,F63,F7,F82` passed with 0 errors.

---

## Week 8: Multilingual Reranker Sweep & Head-to-Head Architectural Comparison

### 1. Overview & Problem Definition

In Week 8, we evaluated DevPilot's retrieval subsystem across a 100-query multilingual gold-standard benchmark (`benchmarks/multilingual_gold_100.jsonl`), comprising 34 English technical queries, 33 native Bengali script queries, and 33 Romanized Banglish queries.

Initial analysis revealed an acute linguistic divergence: while the monolingual English cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) performed exceptionally on English and Banglish (1.0000 MRR), it caused a catastrophic rank drop on native Bengali script (collapsing to **0.2788 MRR** and **0.4848 Recall@5**, inducing 19 ranking demotions) due to subword tokenization fragmentation and Latin loanword bias.

To solve this, we implemented and empirically evaluated three successive remediation architectures against the baseline.

### 2. Definitive 4-Way Architectural Comparison Matrix

All four configurations were benchmarked end-to-end on the identical 100-query corpus using [`scripts/benchmark_head_to_head.py`](scripts/benchmark_head_to_head.py), with telemetry preserved in [`artifacts/head_to_head_comparison.json`](artifacts/head_to_head_comparison.json):

| Metric | 1. Baseline (Un-guarded Monolingual) | 2. Approach A (Script-Aware Bypass) | 3. Approach B (Multilingual CE) | 4. Approach A+B Hybrid (Production Champion) |
| :--- | :---: | :---: | :---: | :---: |
| **Model Checkpoint** | `ms-marco-MiniLM-L-6-v2` | `ms-marco-MiniLM-L-6-v2` | `mmarco-mMiniLMv2-L12-H384-v1` | `mmarco-mMiniLMv2-L12-H384-v1` |
| **Backbone Architecture** | BERT (MiniLM-L6) | BERT (MiniLM-L6) | XLM-RoBERTa (mMiniLMv2-L12) | XLM-RoBERTa (mMiniLMv2-L12) |
| **Transformer Layers** | 6 layers | 6 layers | 12 layers | 12 layers |
| **Active Parameters** | 22,713,601 (22.7M) | 22,713,601 (22.7M) | 117,641,089 (117.6M) | 117,641,089 (117.6M) |
| **FP32 Memory Footprint**| **86.65 MB** | **86.65 MB** | 448.77 MB | 448.77 MB |
| **Global Recall@5** | 0.8300 | 0.9500 | **0.9900** | 0.9800 |
| **Global MRR** | 0.7015 | 0.7630 | 0.8675 | **0.8748** 🏆 |
| **Rank #1 Hits** | 63 / 100 (63.0%) | 64 / 100 (64.0%) | 79 / 100 (79.0%) | **80 / 100 (80.0%)** 🏆 |
| **English MRR (34 queries)** | **0.8897** | **0.8897** | 0.7922 | **0.8284** *(+4.6%)* |
| **Bangla MRR (33 queries)** | 0.2788 ❌ | 0.4652 *(+66.9%)* | **0.9051** 🚀 *(+224.6%)* | **0.8581** *(+207.8%)* |
| **Banglish MRR (33 queries)**| 0.9303 | 0.9303 | 0.9076 | **0.9394** 🚀 *(+3.5%)* |
| **Bangla Recall@5** | 0.4848 ❌ | 0.8485 | **0.9697** | **0.9697** |
| **P50 Retrieval Latency**| 182.21 ms | **148.65 ms** ⚡ | 221.35 ms | 232.12 ms |
| **P95 Retrieval Latency**| 244.64 ms | **191.12 ms** ⚡ | 419.55 ms | 419.04 ms *(< 500ms SLA)* |

### 3. Architectural Rationale & Engineering Deep-Dive

#### A. Tokenizer Mechanics: XLM-R SentencePiece (250k Vocab) vs. BERT WordPiece (30k Vocab)
- **WordPiece Fragmentation:** `ms-marco-MiniLM-L-6-v2` utilizes a 30,522-token English WordPiece vocabulary. Because it lacks Bengali Unicode subwords, it decomposes a standard Bengali word into 4 to 6 character atoms and combining vowel diacritics (`কার`). A 6-word query fragments into 27–50 subwords, dispersing attention matrices across character fragments and destroying semantic phrase understanding.
- **SentencePiece Representation:** `mmarco-mMiniLMv2-L12-H384-v1` employs a 250,000-token SentencePiece vocabulary trained on multilingual corpora. Bengali technical concepts (`_সিস্টেম`, `_ডেটাবেস`, `_মাইগ্রেশন`) are preserved as unified semantic morphemes, allowing cross-attention to evaluate full contextual relevance and elevating Bangla MRR to **0.9051**.

#### B. 12-Layer vs. 6-Layer CPU Latency & Memory Footprint
- MiniLM-L6 (6 layers, 22.7M parameters) consumes only **86.65 MB RAM** in FP32 and achieves **148.65 ms P50 / 191.12 ms P95** under Approach A because native script queries bypass neural inference to execute in ~8 ms via BM25/Vector RRF.
- mMiniLMv2-L12 (12 layers, 117.6M parameters) has double the transformer depth and an $8.2\times$ larger embedding matrix (96M params), requiring **448.77 MB RAM**. On CPU, evaluating 10 candidate pairs per query incurs ~232 ms P50 and ~419 ms P95 latency, which remains well within DevPilot's interactive sub-500ms SLA.

#### C. Neural-Symbolic Consensus: Why 20% RRF Score Blending Outperforms Pure Neural Reranking
- In Configuration 4 (**Approach A+B Hybrid**), candidate scores blend neural cross-attention sigmoid probabilities with normalized Hybrid RRF consensus:
  $$S_{\text{blended}} = (1 - \alpha) \cdot \sigma(S_{\text{CE}}) + \alpha \cdot \text{RRF}_{\text{norm}} \quad (\alpha = 0.20)$$
- Pure cross-encoders occasionally suffer from cross-lingual calibration drifts on technical English passages. Blending 20% RRF consensus ($k=60$ merge of BM25 exact keywords and dense vector embeddings) acts as a regularizing prior, boosting English MRR from 0.7922 back to **0.8284 (+4.6%)** and Banglish MRR to **0.9394 (+3.5%)**, achieving our peak system precision of **0.8748 Global MRR and 80.0% Rank #1 hits**.

### 4. Production Champion Selection

Based on these trade-offs, **Approach A+B Hybrid** is configured as DevPilot's default production retrieval engine in [`src/core/config.py`](src/core/config.py) (`RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"`, `RERANKER_BLEND_RRF_WEIGHT = 0.2`), while **Approach A** remains our documented Edge / Low-Memory deployment profile.


