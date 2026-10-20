"""Head-to-head benchmarking script comparing 4 retrieval configurations:
1. Baseline: Un-guarded monolingual cross-encoder (ms-marco-MiniLM-L-6-v2)
2. Approach A: ms-marco-MiniLM-L-6-v2 + Script-Aware Dynamic Bypass
3. Approach B: Global multilingual cross-encoder (cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)
4. Approach A+B Hybrid: mmarco-mMiniLMv2-L12-H384-v1 with RRF Score Blending
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.metrics import compute_recall_at_k
from src.evaluation.runner import compute_percentile, load_benchmark_dataset
from src.services.embedding import get_embedding_service
from src.services.retrieval.pipeline import retrieve_chunks
from src.services.retrieval.reranker import RerankerService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("head_to_head")


def get_model_footprint(reranker: RerankerService) -> dict[str, Any]:
    """Measure model parameters and FP32 memory footprint."""
    model = reranker._get_model()
    if model is None or not hasattr(model, "model"):
        return {"params": 0, "size_mb": 0.0}

    params = sum(p.numel() for p in model.model.parameters())
    size_mb = sum(p.numel() * p.element_size() for p in model.model.parameters()) / (1024 * 1024)
    return {"params": params, "size_mb": round(size_mb, 2)}


async def evaluate_configuration(
    config_name: str,
    reranker: RerankerService,
    dataset: list[dict[str, Any]],
    corpus: list[dict[str, Any]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Evaluate a single reranker configuration across all queries."""
    logger.info("Evaluating: %s ...", config_name)
    latencies_ms: list[float] = []
    global_recalls: list[float] = []
    global_mrrs: list[float] = []
    rank1_hits = 0

    per_lang: dict[str, dict[str, list[float]]] = {
        "english": {"recalls": [], "mrrs": [], "rank1": []},
        "bangla": {"recalls": [], "mrrs": [], "rank1": []},
        "banglish": {"recalls": [], "mrrs": [], "rank1": []},
    }

    # Pre-warm model with dummy pair
    reranker.rerank("warmup query", [{"chunk_id": "w1", "content": "warmup candidate", "rrf_score": 0.01}], top_k=1)

    for item in dataset:
        query = item["query"]
        ground_truth_ids = set(item.get("ground_truth_chunk_ids") or [])
        lang = item.get("language", "english")
        if lang not in per_lang:
            per_lang[lang] = {"recalls": [], "mrrs": [], "rank1": []}

        t0 = time.perf_counter()
        retrieved = await retrieve_chunks(
            query=query,
            chunks=corpus,
            search_mode="hybrid_rerank",
            top_k=top_k,
            chunk_limit=10,
            reranker=reranker,
        )
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000)

        retrieved_ids = [d.get("chunk_id") or d.get("id") for d in retrieved]

        # Recall@k
        r_k = compute_recall_at_k(retrieved_ids, list(ground_truth_ids), k=top_k)
        global_recalls.append(r_k)
        per_lang[lang]["recalls"].append(r_k)

        # MRR & Rank 1
        found_rank = None
        for idx, doc_id in enumerate(retrieved_ids):
            if doc_id in ground_truth_ids:
                found_rank = idx
                break

        if found_rank is not None:
            rr = 1.0 / (found_rank + 1)
            is_rank1 = 1.0 if found_rank == 0 else 0.0
        else:
            rr = 0.0
            is_rank1 = 0.0

        if is_rank1:
            rank1_hits += 1

        global_mrrs.append(rr)
        per_lang[lang]["mrrs"].append(rr)
        per_lang[lang]["rank1"].append(is_rank1)

    total = len(dataset)
    footprint = get_model_footprint(reranker)

    slice_results = {}
    for l_name, l_data in per_lang.items():
        n = len(l_data["recalls"])
        slice_results[l_name] = {
            "count": n,
            "recall_at_5": round(sum(l_data["recalls"]) / n, 4) if n else 0.0,
            "mrr": round(sum(l_data["mrrs"]) / n, 4) if n else 0.0,
            "rank1_hits": int(sum(l_data["rank1"])),
        }

    return {
        "config_name": config_name,
        "model_name": reranker.model_name,
        "enable_script_bypass": reranker.enable_script_bypass,
        "blend_rrf_weight": reranker.blend_rrf_weight,
        "parameters": footprint["params"],
        "memory_mb": footprint["size_mb"],
        "total_queries": total,
        "recall_at_5": round(sum(global_recalls) / total, 4) if total else 0.0,
        "mrr": round(sum(global_mrrs) / total, 4) if total else 0.0,
        "rank1_hits": rank1_hits,
        "rank1_percent": round((rank1_hits / total) * 100, 2) if total else 0.0,
        "p50_retrieval_ms": compute_percentile(latencies_ms, 50),
        "p95_retrieval_ms": compute_percentile(latencies_ms, 95),
        "slices": slice_results,
    }


async def main() -> None:
    dataset_path = PROJECT_ROOT / "benchmarks" / "multilingual_gold_100.jsonl"
    dataset = load_benchmark_dataset(dataset_path)
    logger.info("Loaded %d gold queries from %s", len(dataset), dataset_path)

    # Build corpus with pre-computed embeddings
    logger.info("Pre-indexing candidate corpus embeddings...")
    embedding_service = get_embedding_service()
    seen_ids = set()
    raw_corpus: list[dict[str, Any]] = []

    for item in dataset:
        for chunk_id in item.get("ground_truth_chunk_ids", []):
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                raw_corpus.append({
                    "chunk_id": chunk_id,
                    "content": item.get("reference_answer", "") or f"Document context for {chunk_id}",
                    "project_id": "benchmark_project",
                })

    corpus_texts = [c["content"] for c in raw_corpus]
    corpus_embeddings = await embedding_service.generate_embeddings(corpus_texts)
    for c, emb in zip(raw_corpus, corpus_embeddings):
        c["embedding"] = emb

    logger.info("Corpus ready: %d unique chunks indexed.", len(raw_corpus))

    # Initialize the 4 configurations
    configs = [
        (
            "1. Baseline (Un-guarded Monolingual)",
            RerankerService(
                model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
                enable_script_bypass=False,
                blend_rrf_weight=0.0,
            ),
        ),
        (
            "2. Approach A (Script-Aware Bypass)",
            RerankerService(
                model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
                enable_script_bypass=True,
                blend_rrf_weight=0.0,
            ),
        ),
        (
            "3. Approach B (Multilingual Cross-Encoder)",
            RerankerService(
                model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                enable_script_bypass=False,
                blend_rrf_weight=0.0,
            ),
        ),
        (
            "4. Approach A+B (RRF-Blended Multilingual)",
            RerankerService(
                model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                enable_script_bypass=False,
                blend_rrf_weight=0.2,
            ),
        ),
    ]

    results = []
    for name, reranker in configs:
        res = await evaluate_configuration(name, reranker, dataset, raw_corpus, top_k=5)
        results.append(res)

    # Persist JSON results
    output_path = PROJECT_ROOT / "artifacts" / "head_to_head_comparison.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}, f, indent=2)
    logger.info("Results persisted to: %s", output_path)

    # Print summary table
    print("\n" + "=" * 125)
    print("DevPilot Week 8: Head-to-Head Architecture Benchmark Comparison")
    print("=" * 125)
    hdr = f"{'Configuration':<42} | {'Params':<8} | {'RAM (MB)':<8} | {'Recall@5':<8} | {'MRR':<7} | {'P50 (ms)':<9} | {'P95 (ms)':<9} | {'Rank 1 Hits':<11}"
    print(hdr)
    print("-" * 125)
    for r in results:
        params_str = f"{r['parameters'] / 1e6:.1f}M"
        line = (
            f"{r['config_name']:<42} | {params_str:<8} | {r['memory_mb']:<8.1f} | "
            f"{r['recall_at_5']:<8.4f} | {r['mrr']:<7.4f} | {r['p50_retrieval_ms']:<9.2f} | "
            f"{r['p95_retrieval_ms']:<9.2f} | {r['rank1_hits']}/{r['total_queries']} ({r['rank1_percent']}%)"
        )
        print(line)
    print("=" * 125)

    print("\n" + "=" * 90)
    print("Slice-Specific MRR Breakdown Across Configurations")
    print("=" * 90)
    hdr_slices = f"{'Configuration':<42} | {'English MRR':<13} | {'Bangla MRR':<13} | {'Banglish MRR':<13}"
    print(hdr_slices)
    print("-" * 90)
    for r in results:
        en_mrr = r["slices"]["english"]["mrr"]
        bn_mrr = r["slices"]["bangla"]["mrr"]
        bg_mrr = r["slices"]["banglish"]["mrr"]
        print(f"{r['config_name']:<42} | {en_mrr:<13.4f} | {bn_mrr:<13.4f} | {bg_mrr:<13.4f}")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
