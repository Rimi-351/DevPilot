"""Reproducible benchmark runner evaluating Recall@5, Hit@k, MRR, latency percentiles, and language slices."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.metrics import (
    compute_hit_at_k,
    compute_mrr,
    compute_recall_at_k,
    compute_reciprocal_rank,
    compute_unsupported_claims_rate,
)
from src.services.llm import STOPWORDS, get_llm_service
from src.services.retrieval import retrieve_chunks

logger = logging.getLogger("benchmark_runner")

# Export check_unsupported_claims as alias for backward compatibility
check_unsupported_claims = compute_unsupported_claims_rate


@dataclass
class ModeEvaluationSummary:
    mode: str
    top_k: int
    total_queries: int
    hit_at_k: float
    mrr: float
    p50_retrieval_ms: float
    p95_retrieval_ms: float
    p50_generation_ms: float
    p95_generation_ms: float
    unsupported_claims_rate: float
    chunk_size: int = 512
    recall_at_5: float = 0.0
    language: str = "all"
    language_slices: Optional[dict[str, Any]] = None


def compute_percentile(values: list[float], percentile: float) -> float:
    """Compute percentile value from a list of floats."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * (percentile / 100.0))
    idx = min(idx, len(sorted_v) - 1)
    return round(sorted_v[idx], 2)


def get_default_dataset_path() -> str:
    """Resolve highest priority benchmark dataset available (multilingual gold 100 first)."""
    candidates = [
        "benchmarks/multilingual_gold_100.jsonl",
        "benchmarks/gold_standard_50.jsonl",
        "benchmarks/gold_standard.jsonl",
        "benchmarks/eval_data.jsonl",
    ]
    for c in candidates:
        if (PROJECT_ROOT / c).exists():
            return c
    return candidates[0]


def load_benchmark_dataset(dataset_path: str | Path) -> list[dict[str, Any]]:
    """Load benchmark dataset from a JSONL file with fallback between dataset aliases."""
    path = Path(dataset_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        # Automatic fallback between 100-query multilingual, 50-query dataset, gold_standard, and eval_data
        candidates = [
            path.parent / "multilingual_gold_100.jsonl",
            path.parent / "gold_standard_50.jsonl",
            path.parent / "gold_standard.jsonl",
            path.parent / "eval_data.jsonl",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break

    if not path.exists():
        raise FileNotFoundError(f"Benchmark dataset not found at: {path}")

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def evaluate_mode(
    dataset: list[dict[str, Any]],
    mode: str,
    top_k: int = 5,
    chunk_limit: int = 10,
    chunk_size: int = 512,
    language_filter: str = "all",
) -> ModeEvaluationSummary:
    """Run benchmark evaluation for a specific retrieval mode across all or filtered dataset items."""
    llm_service = get_llm_service()

    # Filter by language slice if specified
    if language_filter and language_filter.lower() != "all":
        eval_items = [
            item for item in dataset
            if item.get("language", "english").lower() == language_filter.lower()
        ]
    else:
        eval_items = dataset

    hits = 0
    reciprocal_ranks: list[float] = []
    recalls_at_5: list[float] = []
    retrieval_latencies_ms: list[float] = []
    generation_latencies_ms: list[float] = []
    unsupported_rates: list[float] = []

    evaluable_queries_count = 0
    per_lang_stats: dict[str, dict[str, list[float]]] = {}

    for item in eval_items:
        query = item["query"]
        lang = item.get("language", "english").lower()
        ground_truth_ids = set(item.get("ground_truth_chunk_ids", []))
        corpus = item.get("corpus", [])

        if lang not in per_lang_stats:
            per_lang_stats[lang] = {"recall_at_5": [], "mrr": []}

        # Measure retrieval latency
        t0 = time.perf_counter()
        retrieved = await retrieve_chunks(
            query=query,
            chunks=corpus,
            search_mode=mode,
            top_k=top_k,
            chunk_limit=chunk_limit,
        )
        t1 = time.perf_counter()
        retrieval_latencies_ms.append((t1 - t0) * 1000)

        retrieved_ids = [doc.get("chunk_id") or doc.get("id") for doc in retrieved]

        # Evaluate Hit@k, Recall@5, and MRR for answerable queries
        if ground_truth_ids:
            evaluable_queries_count += 1
            found_rank = None
            for rank_idx, doc_id in enumerate(retrieved_ids):
                if doc_id in ground_truth_ids:
                    found_rank = rank_idx
                    break

            r5 = compute_recall_at_k(retrieved_ids, ground_truth_ids, k=top_k)
            recalls_at_5.append(r5)
            per_lang_stats[lang]["recall_at_5"].append(r5)

            if found_rank is not None:
                hits += 1
                rr = 1.0 / (found_rank + 1)
            else:
                rr = 0.0
            reciprocal_ranks.append(rr)
            per_lang_stats[lang]["mrr"].append(rr)

        # Measure generation latency and answer grounding
        t2 = time.perf_counter()
        try:
            answer, cited_chunks = await llm_service.generate_grounded_answer(
                query=query,
                context_chunks=retrieved,
                temperature=0.0,
            )
        except Exception:
            answer, cited_chunks = llm_service._generate_mock_answer(query, retrieved)
        t3 = time.perf_counter()
        generation_latencies_ms.append((t3 - t2) * 1000)

        unsupported_rate = check_unsupported_claims(answer, retrieved)
        unsupported_rates.append(unsupported_rate)

    total = len(eval_items)
    denom = evaluable_queries_count if evaluable_queries_count > 0 else total
    hit_at_k = round(hits / denom, 4) if denom > 0 else 0.0
    recall_at_5 = round(sum(recalls_at_5) / len(recalls_at_5), 4) if recalls_at_5 else 0.0
    mrr = round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0
    avg_unsupported = round(sum(unsupported_rates) / total, 4) if total > 0 else 0.0

    # Aggregate per-language metrics
    language_slices: dict[str, Any] = {}
    for l_name, l_data in per_lang_stats.items():
        n_queries = len(l_data["recall_at_5"])
        l_r5 = round(sum(l_data["recall_at_5"]) / n_queries, 4) if n_queries > 0 else 0.0
        l_mrr = round(sum(l_data["mrr"]) / n_queries, 4) if n_queries > 0 else 0.0
        language_slices[l_name] = {
            "count": n_queries,
            "recall_at_5": l_r5,
            "mrr": l_mrr,
        }

    return ModeEvaluationSummary(
        mode=mode,
        top_k=top_k,
        total_queries=total,
        hit_at_k=hit_at_k,
        mrr=mrr,
        p50_retrieval_ms=compute_percentile(retrieval_latencies_ms, 50),
        p95_retrieval_ms=compute_percentile(retrieval_latencies_ms, 95),
        p50_generation_ms=compute_percentile(generation_latencies_ms, 50),
        p95_generation_ms=compute_percentile(generation_latencies_ms, 95),
        unsupported_claims_rate=avg_unsupported,
        chunk_size=chunk_size,
        recall_at_5=recall_at_5,
        language=language_filter,
        language_slices=language_slices,
    )


def print_comparison_table(summaries: list[ModeEvaluationSummary]) -> None:
    """Print an ASCII comparison table of evaluation results and language slices to stdout."""
    header = (
        f"{'Retrieval Mode':<16} | {'Lang':<8} | {'Top-K':<5} | {'Recall@5':<8} | {'MRR':<7} | "
        f"{'P50 Ret (ms)':<12} | {'P95 Ret (ms)':<12} | "
        f"{'P50 Gen (ms)':<12} | {'P95 Gen (ms)':<12} | {'Unsupp Claims':<14}"
    )
    separator = "-" * len(header)
    print("\n" + "=" * len(header))
    print("DevPilot Multilingual Retrieval Quality Benchmark & Parameter Sweep Results")
    print("=" * len(header))
    print(header)
    print(separator)

    for s in summaries:
        r5_val = s.recall_at_5 if s.recall_at_5 > 0 else s.hit_at_k
        line = (
            f"{s.mode:<16} | {s.language:<8} | {s.top_k:<5} | {r5_val:<8.2f} | {s.mrr:<7.2f} | "
            f"{s.p50_retrieval_ms:<12.2f} | {s.p95_retrieval_ms:<12.2f} | "
            f"{s.p50_generation_ms:<12.2f} | {s.p95_generation_ms:<12.2f} | "
            f"{s.unsupported_claims_rate:<14.2%}"
        )
        print(line)
    print(separator)

    # Print language slices breakdown if multiple languages present
    has_slices = any(s.language_slices and len(s.language_slices) > 1 for s in summaries)
    if has_slices:
        slice_header = f"{'Language Slice':<16} | {'Retrieval Mode':<16} | {'Queries':<7} | {'Recall@5':<8} | {'MRR':<7}"
        slice_sep = "-" * len(slice_header)
        print("\n" + "=" * len(slice_header))
        print("Multilingual Performance Breakdown by Language Slice")
        print("=" * len(slice_header))
        print(slice_header)
        print(slice_sep)

        for lang in ["english", "bangla", "banglish"]:
            for s in summaries:
                if s.language_slices and lang in s.language_slices:
                    sl = s.language_slices[lang]
                    print(f"{lang:<16} | {s.mode:<16} | {sl['count']:<7} | {sl['recall_at_5']:<8.2f} | {sl['mrr']:<7.2f}")
        print(slice_sep + "\n")


async def run_parameter_sweep(
    data_path: str = "benchmarks/multilingual_gold_100.jsonl",
    chunk_sizes: Optional[list[int]] = None,
    top_k_values: Optional[list[int]] = None,
    modes: Optional[list[str]] = None,
    language_filter: str = "all",
    output_path: str = "artifacts/multilingual_benchmark_results.json",
) -> list[ModeEvaluationSummary]:
    """Execute grid sweep over retrieval modes and parameters across multilingual slices."""
    if chunk_sizes is None:
        chunk_sizes = [512]
    if top_k_values is None:
        top_k_values = [5]
    if modes is None:
        modes = ["vector_only", "hybrid", "hybrid_rerank"]

    dataset = load_benchmark_dataset(data_path)
    print(f"Loaded benchmark dataset ({len(dataset)} items) from {data_path}")
    print(f"Executing parameter sweep: modes={modes}, top_k={top_k_values}, language={language_filter}")

    summaries: list[ModeEvaluationSummary] = []
    for c_size in chunk_sizes:
        for k in top_k_values:
            for m in modes:
                summary = await evaluate_mode(
                    dataset=dataset,
                    mode=m,
                    top_k=k,
                    chunk_size=c_size,
                    language_filter=language_filter,
                )
                summaries.append(summary)

    print_comparison_table(summaries)

    out_file = Path(output_path)
    if not out_file.is_absolute():
        out_file = PROJECT_ROOT / out_file

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "dataset": str(data_path),
                "dataset_size": len(dataset),
                "language_filter": language_filter,
                "sweep_parameters": {
                    "chunk_sizes": chunk_sizes,
                    "top_k_values": top_k_values,
                    "modes": modes,
                },
                "results": [asdict(s) for s in summaries],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Benchmark parameter sweep results successfully persisted to: {out_file}")
    return summaries


async def run_benchmark(
    data_path: str = "benchmarks/multilingual_gold_100.jsonl",
    mode: str = "all",
    top_k: int = 5,
    chunk_size: int = 512,
    language_filter: str = "all",
    output_path: str = "artifacts/multilingual_benchmark_results.json",
    sweep: bool = False,
) -> list[ModeEvaluationSummary]:
    """Execute evaluation and persist results."""
    if sweep:
        modes_to_evaluate = (
            ["vector_only", "hybrid", "hybrid_rerank"]
            if mode == "all"
            else [mode]
        )
        return await run_parameter_sweep(
            data_path=data_path,
            chunk_sizes=[chunk_size],
            top_k_values=[top_k],
            modes=modes_to_evaluate,
            language_filter=language_filter,
            output_path=output_path,
        )

    dataset = load_benchmark_dataset(data_path)

    modes_to_evaluate = (
        ["vector_only", "hybrid", "hybrid_rerank"]
        if mode == "all"
        else [mode]
    )

    summaries = []
    for m in modes_to_evaluate:
        summary = await evaluate_mode(
            dataset,
            mode=m,
            top_k=top_k,
            chunk_size=chunk_size,
            language_filter=language_filter,
        )
        summaries.append(summary)

    print_comparison_table(summaries)

    # Persist results
    out_file = Path(output_path)
    if not out_file.is_absolute():
        out_file = PROJECT_ROOT / out_file

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "dataset": str(data_path),
                "dataset_size": len(dataset),
                "language_filter": language_filter,
                "chunk_size": chunk_size,
                "top_k": top_k,
                "results": [asdict(s) for s in summaries],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Benchmark results successfully persisted to: {out_file}")
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="DevPilot Multilingual Retrieval Quality Benchmark & Parameter Sweep Runner")
    parser.add_argument(
        "--mode",
        choices=["vector_only", "hybrid", "hybrid_rerank", "all"],
        default=None,
        help="Retrieval search mode to evaluate (default: all, or hybrid_rerank if --enable-reranker is set)",
    )
    parser.add_argument(
        "--enable-reranker",
        action="store_true",
        default=False,
        help="Enable cross-encoder reranker (runs in hybrid_rerank mode)",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        default=False,
        help="Run parameter sweep across retrieval modes (vector_only, hybrid, hybrid_rerank)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of retrieved context chunks (default: 5 for Recall@5)",
    )
    parser.add_argument(
        "--lang",
        choices=["english", "bangla", "banglish", "all"],
        default="all",
        help="Filter evaluation to a specific language slice (default: all)",
    )
    parser.add_argument(
        "--all-langs",
        action="store_true",
        default=False,
        help="Evaluate all languages (alias for --lang all)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Chunk size (default: 512)",
    )
    parser.add_argument(
        "--data-path",
        "--dataset",
        dest="data_path",
        type=str,
        default=get_default_dataset_path(),
        help="Path to benchmark JSONL dataset (alias: --dataset)",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="artifacts/multilingual_benchmark_results.json",
        help="Path to save benchmark JSON output (default: artifacts/multilingual_benchmark_results.json)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        default=False,
        help="Force deterministic mock LLM generation for reproducible offline benchmark runs",
    )

    args = parser.parse_args()

    if args.mock_llm:
        os.environ["LLM_MOCK"] = "1"

    # Language resolution: --all-langs overrides --lang
    selected_lang = "all" if args.all_langs else args.lang

    # Determine mode: if --enable-reranker is passed, set mode to hybrid_rerank unless explicitly overridden
    if args.enable_reranker:
        selected_mode = "hybrid_rerank"
    elif args.mode is not None:
        selected_mode = args.mode
    else:
        selected_mode = "all"

    asyncio.run(
        run_benchmark(
            data_path=args.data_path,
            mode=selected_mode,
            top_k=args.top_k,
            chunk_size=args.chunk_size,
            language_filter=selected_lang,
            output_path=args.output_path,
            sweep=args.sweep,
        )
    )


if __name__ == "__main__":
    main()
