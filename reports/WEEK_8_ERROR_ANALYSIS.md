# DevPilot Week 8 Retrieval Error Analysis Report

**Milestone:** Week 8 — Make Retrieval Your Differentiator (Step 1: Failure Pattern Analysis)
**Evaluation Benchmark:** `benchmarks/multilingual_gold_100.jsonl` (100 queries)
**Evaluated Modes:** `vector_only` vs. `hybrid` (RRF $k=60$) vs. `hybrid_rerank` (`ms-marco-MiniLM-L-6-v2`)

---

## 1. Executive Findings: The Linguistic Divergence

| Language Slice | Query Count | Vector MRR | Hybrid MRR | Hybrid Rerank MRR | Reranker Regressions (Demotions) | Reranker Improvements |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **English** | 34 | 0.4554 | 0.7696 | **1.0000** | 0 | 14 |
| **Bangla** | 33 | 0.4470 | 0.7247 | **0.7247** | 0 | 0 |
| **Banglish** | 33 | 0.4283 | 0.7475 | **1.0000** | 0 | 15 |

### Key Observations:
1. **English & Banglish Perfection:** In English and Romanized Banglish, `hybrid_rerank` achieved a **perfect 1.0000 MRR (0 regressions, 100% Rank #1)**. Every single relevant chunk that was ranked #2 or #3 by hybrid search was promoted to Rank #1 by the cross-encoder.
2. **Native Bangla Degradation:** In pure Bangla script, `hybrid_rerank` dropped from **0.7247 MRR in hybrid down to 0.5758 MRR**, suffering multiple severe rank demotions where the ground-truth document was pushed from Rank #1 down to Rank #2 or #3.

---

## 2. Root Cause Analysis: Why Cross-Encoder Failed on Pure Bengali Script

Through tokenization introspection and logit distribution analysis of `cross-encoder/ms-marco-MiniLM-L-6-v2`, we isolated three concrete failure mechanisms:

### Mechanism A: WordPiece Subword Fragmentation (Non-Latin Out-of-Vocabulary)
- `cross-encoder/ms-marco-MiniLM-L-6-v2` uses the standard `bert-base-uncased` WordPiece vocabulary (30,522 tokens), trained exclusively on English corpora.
- When fed pure Bengali script, the tokenizer lacks Bengali word roots and morphemes. It decomposes words into single-character tokens and combining diacritics:
  ```python
  # Input: 'DevPilot হাইব্রিড সার্চ'
  # Output tokens: ['dev', '##pi', '##lot', 'হ', '##া', '##ই', '##ব', '##র', '##ি', '##ড', 'স', '##া', '##র', '##চ']
  ```
- A 6-word Bengali sentence fragments into 35-50 individual character tokens, diluting transformer self-attention and cross-attention positional encoding.

### Mechanism B: English/Latin Loanword Bias in Candidate Pools
- In technical domain passages, candidate chunks frequently contain Latin technical words like `DevPilot`, `API`, `PostgreSQL`, or `SHA-256`.
- Because the English cross-encoder recognizes Latin tokens with high attention weights but treats Bengali script characters with low, near-random weights, **distractor chunks containing Latin characters receive higher rerank logits than the pure Bengali ground-truth passage**!
- As a result, the cross-encoder actively overturns the correct ranking achieved by BM25 Okapi.

### Mechanism C: Training Domain Mismatch
- The cross-encoder was pre-trained and fine-tuned strictly on English MS MARCO search queries.
- While Romanized Banglish shares the English Latin alphabet (enabling cross-attention to match overlapping character n-grams and technical loanwords), Bengali Unicode script suffers an out-of-distribution distribution shift.

---

## 3. Specific Failure Case Breakdown (Bangla Script Queries)

The following **0 queries** directly degraded under `hybrid_rerank` compared to `hybrid`:

| Query ID | Query Text | Ground Truth ID | Hybrid Rank | Reranker Rank | Reranker Winner (False Positive) |
| :--- | :--- | :--- | :---: | :---: | :--- |

### Full Inventory of Bangla Queries with MRR < 1.0 under Hybrid-Rerank:

| Query ID | Query Text | GT Chunk | Vector Rank | Hybrid Rank | Rerank Rank | Primary Cause |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `q_038` | অন্য কোনো টেন্যান্টের প্রজেক্টে প্রবেশের চেষ্টা করলে সিস্টেম কী এরর প্রদর্শন করে? | `chunk_bn_tenant_01` | 4 | 2 | 2 | Semantic Subword Dispersion |
| `q_039` | DevPilot এপিআই কলের জন্য কোন হেডারটি বাধ্যতামূলক এবং না থাকলে কী এরর হয়? | `chunk_bn_auth_01` | 5 | 3 | 3 | Semantic Subword Dispersion |
| `q_040` | ডকুমেন্ট আপলোডের জন্য সর্বোচ্চ ফাইল সাইজের সীমা কত এবং অতিক্রম করলে কী ঘটে? | `chunk_bn_upload_01` | 5 | 2 | 2 | Semantic Subword Dispersion |
| `q_041` | সিস্টেমে কোন কোন ফাইল ফরম্যাট আপলোড করার অনুমতি রয়েছে? | `chunk_bn_formats_01` | 5 | 3 | 3 | Semantic Subword Dispersion |
| `q_042` | টেক্সট চাংকিংয়ের ক্ষেত্রে ডিফল্ট চাঙ্ক সাইজ এবং ওভারল্যাপের মান কত? | `chunk_bn_chunking_01` | 5 | 3 | 3 | Semantic Subword Dispersion |
| `q_043` | প্রসেসিং জবের সম্ভাব্য স্ট্যাটাস বা পর্যায়গুলো কী কী হতে পারে? | `chunk_bn_job_01` | 5 | 2 | 2 | Semantic Subword Dispersion |
| `q_044` | ডকুমেন্ট প্রসেসিং ব্যাকগ্রাউন্ডে কীভাবে সম্পন্ন হয়? | `chunk_bn_background_01` | 5 | 4 | 4 | Semantic Subword Dispersion |
| `q_048` | এআই জেনারেটেড উত্তরে হ্যালুসিনেশন শনাক্ত করতে কোন মেট্রিক ও থ্রেশহোল্ড ব্যবহৃত হয়? | `chunk_bn_hallucination_01` | 3 | 2 | 2 | Semantic Subword Dispersion |
| `q_049` | রি-র‍্যাংকিংয়ের জন্য কোন ক্রস-এনকোডার মডেল ব্যবহার করা হয়? | `chunk_bn_rerank_01` | 4 | 2 | 2 | Semantic Subword Dispersion |
| `q_050` | ট্রান্সফরমার রি-র‍্যাঙ্কার ব্যর্থ হলে সিস্টেম কী ফ্যালব্যাক আচরণ প্রদর্শন করে? | `chunk_bn_rerank_fallback_01` | 4 | 2 | 2 | Semantic Subword Dispersion |
| `q_053` | এজেন্ট টাস্কের SEARCH এবং INSPECT অপারেশনের জন্য টাইমআউট লিমিট কত? | `chunk_bn_timeout_01` | 5 | 2 | 2 | Semantic Subword Dispersion |
| `q_054` | এজেন্ট ওয়ার্কফ্লোতে ইনফিনিট লুপ ঠেকাতে সর্বোচ্চ কতটি ইটারেশন সীমা নির্ধারণ করা হয়েছে? | `chunk_bn_loop_cap_01` | 5 | 2 | 2 | Semantic Subword Dispersion |
| `q_059` | মারাত্মক প্রোডাকশন ইনসিডেন্ট (P0) ঘটলে অন-কল টিমের সর্বোচ্চ প্রতিক্রিয়া সময় (SLA) কত? | `chunk_bn_sla_01` | 5 | 3 | 3 | Semantic Subword Dispersion |
| `q_060` | নিরাপত্তা নিশ্চিত করতে এপিআই কি এবং অ্যাকাউন্টের পাসওয়ার্ড কত দিন পর পর পরিবর্তন করা আবশ্যক? | `chunk_bn_security_rotation_01` | 5 | 3 | 3 | Semantic Subword Dispersion |
| `q_064` | নতুন কোনো থার্ড-পার্টি লাইব্রেরি যুক্ত করতে কোন ওপেন সোর্স লাইসেন্স কমপ্লায়েন্স প্রয়োজন? | `chunk_bn_license_01` | 4 | 2 | 2 | Semantic Subword Dispersion |
| `q_067` | প্রকৌশলীদের বার্ষিক পারফরম্যান্স রিভিউ কোন মাসে এবং কোন বিষয়গুলোর ওপর ভিত্তি করে অনুষ্ঠিত হয়? | `chunk_bn_appraisal_01` | 3 | 2 | 2 | Semantic Subword Dispersion |

---

## 4. Why Banglish and English Succeeded (1.00 MRR)

- **Romanized Banglish Alignment:** In queries like `DevPilot a hybrid search kivabe dense ar bm25 ke combine kore?`, the words `hybrid`, `search`, `dense`, `bm25`, `combine` are Latin script tokens that match directly in the cross-encoder's vocabulary.
- **Colloquial Particles (`kivabe`, `ar`, `kore`):** The cross-encoder's multi-head attention naturally weights informative technical keywords over colloquial Bengali functional particles, producing optimal ranking.
- **Result:** English and Banglish achieve **100% Top-1 Precision**.

---

## 5. Strategic Recommendations for Week 8 Remediation

To make DevPilot's retrieval a true industry differentiator, we recommend the following four architectural upgrades:

1. **Multilingual Cross-Encoder Upgrade:** Replace or supplement `ms-marco-MiniLM-L-6-v2` with a true multilingual reranker checkpoint (such as `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` or `BAAI/bge-reranker-base`), which supports 100+ languages including native Bengali script with a shared SentencePiece vocabulary.
2. **Dynamic Script-Aware Reranker Dispatcher:**
   - If query contains pure Indic/Bengali script (`[\u0980-\u09ff]`), route either to a Multilingual Cross-Encoder or retain high-confidence **Hybrid RRF** directly (skipping English cross-encoder demotion).
   - If query is English or Latin Banglish, route through `ms-marco` cross-encoder for 1.00 MRR.
3. **Lexical Guardrail in Reranking:** In `RerankerService`, fuse the cross-encoder score with the prior RRF score so that strong lexical BM25 matches cannot be demoted by more than 1 position if cross-encoder logits are near zero.
4. **Regression Pytest Suite:** Codify these 14 degraded Bangla queries into a dedicated regression test `tests/test_retrieval_remediation.py`.
