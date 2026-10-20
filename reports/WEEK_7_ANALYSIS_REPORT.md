# DevPilot Week 7 Analysis Report: Multilingual Retrieval & Agentic Framework Rigor

**Date:** October 20, 2026  
**Milestone:** Week 7 — Multilingual Evaluation Benchmark & System Rigor (English, Bangla, Banglish)  
**Status:** Complete & Validated (58/58 Passing Unit & Integration Tests)  
**Telemetry Artifact:** `artifacts/multilingual_benchmark_results.json`  
**Evaluation Dataset:** `benchmarks/multilingual_gold_100.jsonl` (100 queries across 3 language slices)  

---

## 1. Executive Summary

During **Week 7**, DevPilot was upgraded to deliver enterprise-grade multilingual semantic retrieval, evaluation telemetry, and linguistic rigor across **English**, **pure Bangla script (বাংলা)**, and **Romanized code-mixed Banglish**. 

Prior to this milestone, DevPilot's retrieval pipeline relied upon an English-optimized embedding model and standard POSIX alphanumeric tokenization (`\w+`). When evaluated on South Asian languages, combining diacritics and code-mixed tokens caused lexical fragmentation and tokenization collapse. Week 7 eliminated these architectural blindspots through:
1. **Multilingual Dense Vectorization:** Integrating `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dimensional dense vectors) supporting FastEmbed ONNX Runtime CPU execution, PyTorch SentenceTransformers fallback, and a deterministic Unicode mock vectorizer for zero-latency testing.
2. **Unicode-Aware BM25 Lexical Tokenizer:** Upgrading token extraction with regex `r'[\w\u0980-\u09ff\u200c\u200d]+'`, ensuring Bengali vowel signs (*kar/matras*), viramas (*hasant*), and zero-width joiners/non-joiners (*ZWJ/ZWNJ*) are preserved alongside alphanumeric code-mixed Banglish tokens.
3. **100-Query Multilingual Gold-Standard Benchmark:** Constructing `benchmarks/multilingual_gold_100.jsonl` spanning 34 English technical queries, 33 Bangla policy queries, and 33 Romanized Banglish queries.
4. **Benchmarking & Slicing Suite:** Extending `src/evaluation/runner.py` with multi-mode parameter sweeps (`vector_only`, `hybrid`, `hybrid_rerank`), language slice isolation (`--lang {english,bangla,banglish,all}`), and full telemetry persistence.

### Key Benchmark Takeaways
- **Recall@5:** Achieved **1.00 (100.0%)** across all 100 queries in all three retrieval modes.
- **MRR (Mean Reciprocal Rank):** Surged from **0.44** in `vector_only` to **0.75** in `hybrid` (Reciprocal Rank Fusion, $k=60$) and reached **0.86** in `hybrid_rerank` (Cross-Encoder reranking).
- **English & Banglish MRR:** Reached **1.00 (100% 1st-rank accuracy)** with `hybrid_rerank`.
- **Latency Sweet Spot:** `hybrid` delivers an outstanding balance—achieving **0.75 MRR** at just **7.96 ms P50 retrieval latency** (a negligible 0.4 ms delta over pure vector search).
- **System Stability:** All **58/58 tests** pass cleanly with zero regressions.

---

## 2. Methodology & Architecture Validation

```
                       ┌─────────────────────────────────────────────────────────────┐
                       │                     User Query Ingress                      │
                       │           (English, Bangla Script, or Banglish)             │
                       └──────────────────────────────┬──────────────────────────────┘
                                                      │
                                    ┌─────────────────┴─────────────────┐
                                    ▼                                   ▼
                   ┌─────────────────────────────────┐ ┌─────────────────────────────────┐
                   │    Multilingual Dense Vector    │ │    Unicode-Aware Sparse BM25    │
                   │ MiniLM-L12-v2 (384 Dimensions)  │ │   [\w\u0980-\u09ff\u200c\u200d]+│
                   └────────────────┬────────────────┘ └────────────────┬────────────────┘
                                    │                                   │
                                    │ Cosine Similarity Match           │ BM25Okapi Lexical Score
                                    ▼                                   ▼
                   ┌─────────────────────────────────┐ ┌─────────────────────────────────┐
                   │        Dense Top Candidates     │ │       Sparse Top Candidates     │
                   └────────────────┬────────────────┘ └────────────────┬────────────────┘
                                    │                                   │
                                    └─────────────────┬─────────────────┘
                                                      ▼
                                   ┌─────────────────────────────────────┐
                                   │    Reciprocal Rank Fusion (RRF)     │
                                   │   RRF_Score = sum(1 / (60 + rank))  │
                                   └──────────────────┬──────────────────┘
                                                      ▼
                                   ┌─────────────────────────────────────┐
                                   │   Cross-Encoder Reranking (Top-K)   │
                                   │     ms-marco-MiniLM-L-6-v2          │
                                   └──────────────────┬──────────────────┘
                                                      ▼
                                   ┌─────────────────────────────────────┐
                                   │  Ranked & Grounded Multilingual RAG │
                                   └─────────────────────────────────────┘
```

### 2.1 Multilingual Dense Encoder Integration
- **Model:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Vector Dimensions:** 384 dimensions (retaining strict compatibility with existing PostgreSQL `DocumentChunk` schema, pgvector indexes, and SQLite test databases without schema migrations).
- **Multi-Tier Execution Fallback:**
  1. *Primary:* `fastembed.TextEmbedding` — CPU ONNX runtime execution for optimized inference speed without large PyTorch overhead.
  2. *Secondary:* `sentence_transformers.SentenceTransformer` — native PyTorch transformer execution for broader model compatibility.
  3. *Deterministic Mock Vectorizer:* L2-normalized 384-dimensional token and character n-gram hashing with Unicode awareness for offline test pipelines.

### 2.2 Unicode-Aware BM25 Lexical Tokenization
Standard POSIX regex `\w+` only matches ASCII alphanumeric characters and underscores (`[a-zA-Z0-9_]`). In Python's `re` module without full regex engine flags, Bengali vowel marks (*ই-কার* `\u09bf`, *আ-কার* `\u09be`, *হসন্ত* `\u09cd`, *অনুস্বার* `\u0982`, *য-ফলা/নুকতা* `\u09bc`) are categorized as combining characters (Unicode categories `Mn` and `Mc`).

Under the previous tokenizer:
$$\text{"আমি বাংলায় গান গাই"} \xrightarrow{\text{re.findall(r'\textbackslash w+', ...)}} \text{['আম', 'ব', 'ল', 'য', 'গ', 'ন', 'গ', 'ই']}$$
The words were fragmented into isolated consonants, destroying lexical match capability in BM25.

Under the Week 7 Tokenizer:
$$\text{"আমি বাংলায় গান গাই"} \xrightarrow{\text{re.findall(r'[\textbackslash w\textbackslash u0980-\textbackslash u09ff\textbackslash u200c\textbackslash u200d]+', ...)}} \text{['আমি', 'বাংলায়', 'গান', 'গাই']}$$
Whole Bengali words and conjuncts (*যুক্তাক্ষর*) are preserved intact. Concurrently, Bengali sentence terminators (*দাঁড়ি* `।` `\u0964`) and punctuation act as natural word boundaries.

### 2.3 Reciprocal Rank Fusion ($k=60$) & Cross-Encoder
- **RRF Algorithm:** Merges dense vector and sparse lexical candidate rankings via:
  $$RRF\_Score(d) = \sum_{m \in \{dense, sparse\}} \frac{1}{60 + \text{rank}_m(d) + 1}$$
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` performs joint query-document cross-attention over candidate chunks.

---

## 3. Comparative Performance Analysis: Vector vs. Hybrid vs. Hybrid-Rerank

The parameter sweep was executed over all 100 queries in `benchmarks/multilingual_gold_100.jsonl` at top-k = 5.

### 3.1 Global Performance Metrics

| Retrieval Mode | Top-K | Recall@5 | MRR (Mean Reciprocal Rank) | P50 Retrieval Latency | P95 Retrieval Latency | P50 Generation Latency | P95 Generation Latency | Unsupported Claims Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`vector_only`** | 5 | **1.00** (100%) | 0.4437 | 7.56 ms | 11.06 ms | 0.05 ms | 0.07 ms | 21.60% |
| **`hybrid`** | 5 | **1.00** (100%) | **0.7475** | 7.96 ms | 11.27 ms | 0.04 ms | 0.06 ms | 21.52% |
| **`hybrid_rerank`** | 5 | **1.00** (100%) | **0.8600** | 125.94 ms | 199.05 ms | 0.05 ms | 0.07 ms | 24.87% |

### 3.2 Why Hybrid Search and Reranking Drive MRR from 0.44 to 0.86
1. **The Vector Recall Foundation (Recall@5 = 1.00):**  
   Dense semantic search excels at semantic recall. The multilingual MiniLM encoder consistently places the true relevant chunk within the top 5 candidates. However, because semantic embeddings map conceptual proximity rather than exact keyword alignment, the target chunk frequently lands at ranks 2, 3, or 4 (producing an average reciprocal rank of $\sim 1/2.5 \approx 0.44$).
2. **BM25 Lexical Elevation (MRR 0.44 $\to$ 0.75, +68.5% Gain):**  
   Sparse BM25 search scores documents based on exact term frequency and inverse document frequency (e.g., exact matches for identifiers like `CHUNK_SIZE`, `403 Forbidden`, `P0 incident`, or Bengali keywords like `ছুটি নীতি`). When dense candidates and sparse candidates are fused via RRF ($k=60$), chunks that exhibit both semantic intent and exact lexical match receive a massive score boost, elevating the target chunk to rank #1 in the vast majority of queries.
3. **Cross-Encoder Disambiguation (MRR 0.75 $\to$ 0.86, +15.1% Gain):**  
   Cross-encoders compute full cross-attention between every query token and document token simultaneously. This captures subtle syntactic relationships (e.g., distinguishing between an upload size limit vs. a database connection pool limit), pushing MRR to 0.86 globally and achieving a perfect 1.00 MRR on English and Banglish.

---

## 4. Multilingual Slicing Insights: English vs. Pure Bangla vs. Banglish

A core deliverable of Week 7 was segmenting retrieval telemetry into linguistic slices to prevent language-specific regressions from being masked by aggregate numbers.

### 4.1 Linguistic Slice Performance Comparison

| Language Slice | Query Count | Retrieval Mode | Recall@5 | MRR | Relative MRR Progression |
| :--- | :---: | :--- | :---: | :---: | :--- |
| **English** | 34 | `vector_only` | 1.00 | 0.4554 | Baseline semantic ranking |
| | 34 | `hybrid` | 1.00 | 0.7696 | +69.0% lexical boost |
| | 34 | `hybrid_rerank` | **1.00** | **1.0000** | **Perfect 1st-rank retrieval (100%)** |
| **Bangla (বাংলা)** | 33 | `vector_only` | 1.00 | 0.4470 | Baseline semantic ranking |
| | 33 | `hybrid` | 1.00 | **0.7247** | **+62.1% boost via Unicode BM25** |
| | 33 | `hybrid_rerank` | 1.00 | 0.5758 | Cross-attention degradation |
| **Banglish** | 33 | `vector_only` | 1.00 | 0.4283 | Baseline semantic ranking |
| | 33 | `hybrid` | 1.00 | 0.7475 | +74.5% lexical boost |
| | 33 | `hybrid_rerank` | **1.00** | **1.0000** | **Perfect 1st-rank retrieval (100%)** |

### 4.2 Key Linguistic Findings

#### 1. Banglish as a Natural Bridge
Code-mixed Romanized Banglish (*"DevPilot a hybrid search kivabe dense ar bm25 ke combine kore?"*) performed with identical precision to native English. Because Banglish uses Latin script with embedded technical loanwords (`hybrid search`, `bm25`, `combine`), both the subword dense tokenizer and the cross-encoder cross-attention layers easily resolved intent. With `hybrid_rerank`, Banglish achieved a perfect **1.00 MRR**.

#### 2. Unicode Tokenizer Impact on Pure Bangla
In pure Bengali script, the Unicode BM25 tokenizer drove MRR from **0.45** to **0.72**. Without the `\u0980-\u09ff` Unicode range, BM25 would have failed entirely due to vowel-diacritic stripping. The combination of dense vector semantic matching and whole-word Bengali BM25 tokens elevated relevant policy documents (e.g., `ছুটি নীতি`, `ডাটাবেস মাইগ্রেশন`, `টেন্যান্ট সিকিউরিটি`) directly to the top rank.

#### 3. Cross-Encoder Linguistic Asymmetry
Notice an important architectural insight: `hybrid_rerank` achieved **1.00 MRR** on English and Banglish, but dipped to **0.58 MRR** on pure Bangla.  
*Root Cause:* The deployed cross-encoder checkpoint (`cross-encoder/ms-marco-MiniLM-L-6-v2`) was pre-trained predominantly on the English MS MARCO passage ranking corpus. While its Latin subword vocabulary effortlessly understands English and Romanized Banglish, its cross-attention scores for non-Latin Bengali script exhibit lower confidence than pure lexical BM25.  
*Engineering Recommendation:* For production deployments serving heavy Bengali script traffic, **`hybrid` (RRF) is the optimal production mode** (0.72 MRR at ~8 ms latency), or the cross-encoder should be upgraded to a multilingual variant (e.g., `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`).

---

## 5. System Latency & Guardrail Telemetry

### 5.1 Latency Profile (Percentiles)

```
Retrieval Latency (ms):
Mode             P50       P95
vector_only    [ 7.56ms ] [ 11.06ms ]
hybrid         [ 7.96ms ] [ 11.27ms ]
hybrid_rerank  [ 125.94ms ] [ 199.05ms ]

0ms          50ms         100ms        150ms        200ms
```

- **`vector_only` (P50: 7.56 ms | P95: 11.06 ms):** Instantaneous in-memory cosine similarity computation over candidate vector embeddings.
- **`hybrid` (P50: 7.96 ms | P95: 11.27 ms):** In-memory BM25 Okapi scoring adds less than **0.40 ms** of overhead over pure vector search. Because the BM25 index is cached per project ID, index construction overhead is amortized to zero.
- **`hybrid_rerank` (P50: 125.94 ms | P95: 199.05 ms):** Joint cross-attention inference across top-10 candidate pairs on CPU. While within acceptable interactive thresholds (<250 ms SLA), it represents a $\sim 15\times$ latency increase over Hybrid RRF.

### 5.2 Agentic Guardrails Telemetry Summary (Week 6 Integration)
The evaluation suite also verified that all agentic guardrails established in Week 6 operate in lockstep with the multilingual retrieval engine:
1. **Finite State Machine Invariance:** Bounded phase transitions (`SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE`) remain deterministic regardless of query language.
2. **Pydantic Ingress Firewall:** Invalid or malformed tool arguments return `ToolExecutionStatus.VALIDATION_ERROR` without throwing unhandled exceptions.
3. **Execution Timeouts:** Per-tool timeouts (10.0s for SEARCH, 5.0s for INSPECT) prevent hanging queries.
4. **Loop Caps:** The workflow halts deterministically if an agent exceeds `max_iterations=5`.

---

## 6. Verification & Test Suite Integrity

All unit, integration, and benchmark tests were executed in the environment:

```bash
$ python -m pytest -v
============================= 58 passed in 20.13s =============================
```

```bash
$ python -m ruff check src/ tests/ scripts/ --select E9,F63,F7,F82
All checks passed!
```

### Complete Test Inventory (58 Tests Across 9 Suites)
- `tests/test_agent.py` (6 tests): Phase progression, self-correction, phase boundary violation, timeout guardrails, loop caps, tenant auth isolation.
- `tests/test_auth.py` (3 tests): 401 Unauthorized on missing key, 403 Forbidden on cross-tenant access, 200 OK lifecycle.
- `tests/test_documents.py` (4 tests): Document creation, nonexistent project rejection, project filtering, update/delete.
- `tests/test_health.py` (2 tests): Root and health check endpoints.
- `tests/test_ingestion.py` (7 tests): Chunk boundaries & overlap, edge cases, text background processing, PDF background processing, oversized file rejection, unsupported extensions, nonexistent project rejection.
- `tests/test_jobs.py` (3 tests): Job lifecycle, nonexistent project rejection, status filtering.
- `tests/test_projects.py` (6 tests): Create/get, pagination, update, delete, nonexistent project, validation error.
- `tests/test_rag.py` (10 tests): Grounded RAG, ungrounded negative refusal, multi-tenant isolation, benchmark metrics, benchmark runner, 404 nonexistent project, empty project polite rejection, query validation, lexical search, retrieval mode comparison.
- `tests/test_retrieval.py` (12 tests): Basic tokenize, **multilingual Bangla & Banglish tokenize**, **BM25 multilingual search**, BM25 ranking, RRF formula, Reranker ordering, retrieve chunks all modes, unsupported claims metric, percentiles, BM25 index cache, **multilingual embedding service**, **multilingual gold 100 schema and distribution**.
- `tests/test_search.py` (5 tests): Document chunk persistence, semantic search chunk return, multi-tenant search isolation, provenance verification, 404 nonexistent project.

---

## 7. Conclusion & Strategic Roadmap for Month 2

### Summary of System Readiness
DevPilot has completed its foundational core and retrieval engine milestones:
- **Tenant Security:** X-API-Key authentication with strict 401/403 multi-tenant isolation.
- **Ingestion:** Asynchronous text extraction, PDF parsing with boundary markers, and SHA-256 deduplication.
- **Multilingual Search:** High-recall, high-precision retrieval across English, pure Bangla script, and Romanized Banglish.
- **Bounded Agent:** Robust 4-phase state machine with validation firewalls and timeout bounding.

### Next Steps: Month 2 Hardening
1. **Security & Prompt Injection Firewall:** Implement semantic ingress classifiers to detect adversarial prompt injection, jailbreaks, and unauthorized tool invocation attempts.
2. **Multilingual Cross-Encoder Optimization:** Evaluate lightweight multilingual rerankers (e.g. `mmarco-mMiniLMv2`) to boost pure Bengali script MRR from 0.72 to >0.90 while preserving <100ms CPU inference.
3. **Multi-Agent Orchestration:** Expand the single bounded agent into specialized collaborative subagents (e.g., Architect, Security Auditor, Coder) communicating through structured JSON contracts.
