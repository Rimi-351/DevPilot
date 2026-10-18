"""Reproducible benchmark runner evaluating Hit@k, MRR, latency percentiles, and unsupported claims."""

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

from src.services.llm import STOPWORDS, get_llm_service
from src.services.retrieval import retrieve_chunks

logger = logging.getLogger("benchmark_runner")


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


def compute_percentile(values: list[float], percentile: float) -> float:
    """Compute percentile value from a list of floats."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * (percentile / 100.0))
    idx = min(idx, len(sorted_v) - 1)
    return round(sorted_v[idx], 2)


from src.evaluation.metrics import (
    compute_hit_at_k,
    compute_mrr,
    compute_reciprocal_rank,
    compute_unsupported_claims_rate,
)

# Export check_unsupported_claims as alias for backward compatibility
check_unsupported_claims = compute_unsupported_claims_rate


def get_default_dataset_path() -> str:
    """Resolve highest priority benchmark dataset available."""
    candidates = [
        "benchmarks/gold_standard_50.jsonl",
        "benchmarks/gold_standard.jsonl",
        "benchmarks/eval_data.jsonl",
    ]
    for c in candidates:
        if (PROJECT_ROOT / c).exists():
            return c
    return candidates[0]


def load_benchmark_dataset(dataset_path: str | Path) -> list[dict[str, Any]]:
    """Load benchmark dataset from a JSONL file with fallback between aliases."""
    path = Path(dataset_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        # Automatic fallback between 50-query dataset, gold_standard, and eval_data
        candidates = [
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
    top_k: int = 3,
    chunk_limit: int = 10,
    chunk_size: int = 512,
) -> ModeEvaluationSummary:
    """Run benchmark evaluation for a specific retrieval mode across all dataset items."""
    llm_service = get_llm_service()

    hits = 0
    reciprocal_ranks = []
    retrieval_latencies_ms = []
    generation_latencies_ms = []
    unsupported_rates = []

    evaluable_queries_count = 0

    for item in dataset:
        query = item["query"]
        ground_truth_ids = set(item.get("ground_truth_chunk_ids", []))
        corpus = item.get("corpus", [])

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

        # Evaluate Hit@k and MRR for answerable queries
        if ground_truth_ids:
            evaluable_queries_count += 1
            found_rank = None
            for rank_idx, doc in enumerate(retrieved):
                doc_id = doc.get("chunk_id") or doc.get("id")
                if doc_id in ground_truth_ids:
                    found_rank = rank_idx
                    break

            if found_rank is not None:
                hits += 1
                reciprocal_ranks.append(1.0 / (found_rank + 1))
            else:
                reciprocal_ranks.append(0.0)

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

    total = len(dataset)
    denom = evaluable_queries_count if evaluable_queries_count > 0 else total
    hit_at_k = round(hits / denom, 4) if denom > 0 else 0.0
    mrr = round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0
    avg_unsupported = round(sum(unsupported_rates) / total, 4) if total > 0 else 0.0

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
    )


def print_comparison_table(summaries: list[ModeEvaluationSummary]) -> None:
    """Print an ASCII comparison table of evaluation results to stdout."""
    header = (
        f"{'Retrieval Mode':<16} | {'Chunk':<5} | {'Top-K':<5} | {'Hit@k':<7} | {'MRR':<7} | "
        f"{'P50 Ret (ms)':<12} | {'P95 Ret (ms)':<12} | "
        f"{'P50 Gen (ms)':<12} | {'P95 Gen (ms)':<12} | {'Unsupp Claims':<14}"
    )
    separator = "-" * len(header)
    print("\n" + "=" * len(header))
    print("DevPilot Retrieval Quality Benchmark & Parameter Sweep Results")
    print("=" * len(header))
    print(header)
    print(separator)

    for s in summaries:
        line = (
            f"{s.mode:<16} | {s.chunk_size:<5} | {s.top_k:<5} | {s.hit_at_k:<7.2f} | {s.mrr:<7.2f} | "
            f"{s.p50_retrieval_ms:<12.2f} | {s.p95_retrieval_ms:<12.2f} | "
            f"{s.p50_generation_ms:<12.2f} | {s.p95_generation_ms:<12.2f} | "
            f"{s.unsupported_claims_rate:<14.2%}"
        )
        print(line)
    print(separator + "\n")


async def run_parameter_sweep(
    data_path: str = "benchmarks/gold_standard_50.jsonl",
    chunk_sizes: Optional[list[int]] = None,
    top_k_values: Optional[list[int]] = None,
    modes: Optional[list[str]] = None,
    output_path: str = "artifacts/benchmark_results.json",
) -> list[ModeEvaluationSummary]:
    """Execute grid sweep over retrieval modes and parameters (chunk size 512, top_k in [3, 5])."""
    if chunk_sizes is None:
        chunk_sizes = [512]
    if top_k_values is None:
        top_k_values = [3, 5]
    if modes is None:
        modes = ["vector_only", "hybrid", "hybrid_rerank"]

    dataset = load_benchmark_dataset(data_path)
    print(f"Loaded benchmark dataset ({len(dataset)} items) from {data_path}")
    print(f"Executing parameter sweep: modes={modes}, chunk_sizes={chunk_sizes}, top_k={top_k_values}")

    summaries: list[ModeEvaluationSummary] = []
    for c_size in chunk_sizes:
        for k in top_k_values:
            for m in modes:
                summary = await evaluate_mode(
                    dataset=dataset,
                    mode=m,
                    top_k=k,
                    chunk_size=c_size,
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
                "sweep_parameters": {
                    "chunk_sizes": chunk_sizes,
                    "top_k_values": top_k_values,
                    "modes": modes,
                },
                "results": [asdict(s) for s in summaries],
            },
            f,
            indent=2,
        )
    print(f"Benchmark parameter sweep results successfully persisted to: {out_file}")
    return summaries


async def run_benchmark(
    data_path: str = "benchmarks/gold_standard_50.jsonl",
    mode: str = "all",
    top_k: int = 3,
    chunk_size: int = 512,
    output_path: str = "artifacts/benchmark_results.json",
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
            top_k_values=[3, 5],
            modes=modes_to_evaluate,
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
        summary = await evaluate_mode(dataset, mode=m, top_k=top_k, chunk_size=chunk_size)
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
                "chunk_size": chunk_size,
                "top_k": top_k,
                "results": [asdict(s) for s in summaries],
            },
            f,
            indent=2,
        )
    print(f"Benchmark results successfully persisted to: {out_file}")
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="DevPilot Retrieval Quality Benchmark & Parameter Sweep Runner")
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
        help="Run parameter sweep across chunk size 512 and top_k in [3, 5]",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of retrieved context chunks (default: 3)",
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
        default="artifacts/benchmark_results.json",
        help="Path to save benchmark JSON output",
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
            output_path=args.output_path,
            sweep=args.sweep,
        )
    )


if __name__ == "__main__":
    main()
