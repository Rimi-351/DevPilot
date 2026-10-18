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


def compute_percentile(values: list[float], percentile: float) -> float:
    """Compute percentile value from a list of floats."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * (percentile / 100.0))
    idx = min(idx, len(sorted_v) - 1)
    return round(sorted_v[idx], 2)


def check_unsupported_claims(answer: str, retrieved_chunks: list[dict[str, Any]]) -> float:
    """Calculate basic unsupported claims rate.

    Measures fraction of non-stopword answer tokens that do not appear in any retrieved context chunk.
    Returns a score between 0.0 (all claims supported) and 1.0 (completely unsupported).
    """
    if not answer or not retrieved_chunks:
        return 0.0

    # Clean and tokenize answer
    answer_tokens = [
        t for t in re.findall(r"\w+", answer.lower())
        if len(t) > 2 and t not in STOPWORDS and not t.isdigit()
    ]
    if not answer_tokens:
        return 0.0

    # Build context token set
    context_tokens = set()
    for chunk in retrieved_chunks:
        content = chunk.get("content", "").lower()
        context_tokens.update(re.findall(r"\w+", content))

    unsupported_count = sum(1 for t in answer_tokens if t not in context_tokens)
    return round(unsupported_count / len(answer_tokens), 4)


def load_benchmark_dataset(dataset_path: str | Path) -> list[dict[str, Any]]:
    """Load benchmark dataset from a JSONL file with fallback between aliases."""
    path = Path(dataset_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        # Automatic fallback between eval_data.jsonl and gold_standard.jsonl
        if "gold_standard.jsonl" in str(path):
            alt_path = path.parent / "eval_data.jsonl"
            if alt_path.exists():
                path = alt_path
        elif "eval_data.jsonl" in str(path):
            alt_path = path.parent / "gold_standard.jsonl"
            if alt_path.exists():
                path = alt_path

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
) -> ModeEvaluationSummary:
    """Run benchmark evaluation for a specific retrieval mode across all dataset items."""
    llm_service = get_llm_service()

    hits = 0
    reciprocal_ranks = []
    retrieval_latencies_ms = []
    generation_latencies_ms = []
    unsupported_rates = []

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

        # Evaluate Hit@k and MRR
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
        answer, cited_chunks = await llm_service.generate_grounded_answer(
            query=query,
            context_chunks=retrieved,
            temperature=0.0,
        )
        t3 = time.perf_counter()
        generation_latencies_ms.append((t3 - t2) * 1000)

        unsupported_rate = check_unsupported_claims(answer, retrieved)
        unsupported_rates.append(unsupported_rate)

    total = len(dataset)
    hit_at_k = round(hits / total, 4) if total > 0 else 0.0
    mrr = round(sum(reciprocal_ranks) / total, 4) if total > 0 else 0.0
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
    )


def print_comparison_table(summaries: list[ModeEvaluationSummary]) -> None:
    """Print an ASCII comparison table of evaluation results to stdout."""
    header = (
        f"{'Retrieval Mode':<16} | {'Hit@k':<7} | {'MRR':<7} | "
        f"{'P50 Ret (ms)':<12} | {'P95 Ret (ms)':<12} | "
        f"{'P50 Gen (ms)':<12} | {'P95 Gen (ms)':<12} | {'Unsupp Claims':<14}"
    )
    separator = "-" * len(header)
    print("\n" + "=" * len(header))
    print("DevPilot Week 5 Retrieval Benchmark Results")
    print("=" * len(header))
    print(header)
    print(separator)

    for s in summaries:
        line = (
            f"{s.mode:<16} | {s.hit_at_k:<7.2f} | {s.mrr:<7.2f} | "
            f"{s.p50_retrieval_ms:<12.2f} | {s.p95_retrieval_ms:<12.2f} | "
            f"{s.p50_generation_ms:<12.2f} | {s.p95_generation_ms:<12.2f} | "
            f"{s.unsupported_claims_rate:<14.2%}"
        )
        print(line)
    print(separator + "\n")


async def run_benchmark(
    data_path: str = "benchmarks/eval_data.jsonl",
    mode: str = "all",
    top_k: int = 3,
    output_path: str = "artifacts/benchmark_results.json",
) -> list[ModeEvaluationSummary]:
    """Execute evaluation and persist results."""
    dataset = load_benchmark_dataset(data_path)

    modes_to_evaluate = (
        ["vector_only", "hybrid", "hybrid_rerank"]
        if mode == "all"
        else [mode]
    )

    summaries = []
    for m in modes_to_evaluate:
        summary = await evaluate_mode(dataset, mode=m, top_k=top_k)
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
                "top_k": top_k,
                "dataset_size": len(dataset),
                "results": [asdict(s) for s in summaries],
            },
            f,
            indent=2,
        )
    print(f"Benchmark results successfully persisted to: {out_file}")
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="DevPilot Week 5 Retrieval Quality Benchmark Runner")
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
        default="benchmarks/eval_data.jsonl",
        help="Path to benchmark JSONL dataset (alias: --dataset)",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="artifacts/benchmark_results.json",
        help="Path to save benchmark JSON output",
    )

    args = parser.parse_args()

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
            output_path=args.output_path,
        )
    )


if __name__ == "__main__":
    main()
