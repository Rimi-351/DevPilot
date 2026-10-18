"""DevPilot Evaluation & Benchmarks Module."""

from src.evaluation.benchmark import (
    DEFAULT_BENCHMARK_DATASET,
    BenchmarkQuery,
    BenchmarkResult,
    BenchmarkRunner,
    compute_mrr,
    compute_recall_at_k,
    compute_reciprocal_rank,
)

from src.evaluation.metrics import compute_unsupported_claims_rate

__all__ = [
    "DEFAULT_BENCHMARK_DATASET",
    "BenchmarkQuery",
    "BenchmarkResult",
    "BenchmarkRunner",
    "compute_mrr",
    "compute_recall_at_k",
    "compute_reciprocal_rank",
    "compute_unsupported_claims_rate",
]
