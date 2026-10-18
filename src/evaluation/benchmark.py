"""Evaluation harness and retrieval benchmarks for DevPilot RAG pipeline.

Calculates key IR metrics: Recall@k and Mean Reciprocal Rank (MRR).
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class BenchmarkQuery:
    """Benchmark query with ground‑truth metadata for retrieval evaluation.

    Added fields:
    - expected_answer: the ideal answer text for RAG evaluation.
    - category: classification of the test case (standard, boundary_split, lexical_gap, unanswerable).
    """

    id: str
    query: str
    expected_doc: str
    relevant_keywords: list[str]
    evidence: str
    expected_answer: str
    category: str = "standard"


DEFAULT_BENCHMARK_DATASET: list[BenchmarkQuery] = [
    BenchmarkQuery(
        id="q1",
        query="How are database migrations executed with Alembic in DevPilot?",
        expected_doc="alembic_guide.md",
        relevant_keywords=["alembic", "migrations", "sqlalchemy", "schema evolution"],
        evidence="PostgreSQL database migrations using Alembic manage schema evolution. Alembic auto-generates migration scripts from SQLAlchemy 2.0 declarative metadata.",
        expected_answer="Alembic generates migration scripts from SQLAlchemy models and applies them to PostgreSQL databases.",
        category="standard",
    ),
    BenchmarkQuery(
        id="q2",
        query="How is multi-tenant project isolation enforced for search?",
        expected_doc="multi_tenancy.md",
        relevant_keywords=["multi-tenant", "isolation", "project_id", "filtering"],
        evidence="Every document and chunk is strictly partitioned by project_id foreign keys, preventing data leakage across tenant boundaries during semantic queries.",
        expected_answer="Project_id filters ensure each tenant only accesses its own documents.",
        category="standard",
    ),
    BenchmarkQuery(
        id="q3",
        query="What chunk size and overlap are used in sliding-window text segmentation?",
        expected_doc="chunking_spec.md",
        relevant_keywords=["chunk size", "overlap", "sliding window", "offsets"],
        evidence="The chunker slices document text into 500-character segments with 50-character sliding-window overlaps to preserve cross-boundary semantic context.",
        expected_answer="500 characters per chunk with a 50‑character overlap.",
        category="standard",
    ),
    BenchmarkQuery(
        id="q4",
        query="What vector dimension and model are used for fast embeddings?",
        expected_doc="embedding_spec.md",
        relevant_keywords=["fastembed", "dimension", "384", "bge-small-en-v1.5"],
        evidence="DevPilot vector embeddings utilize fastembed with BAAI/bge-small-en-v1.5 generating normalized 384-dimensional dense vectors.",
        expected_answer="Fastembed with BAAI/bge-small-en-v1.5 produces 384‑dimensional vectors.",
        category="standard",
    ),
    BenchmarkQuery(
        id="q5",
        query="How are uploaded files deduplicated in storage?",
        expected_doc="storage_architecture.md",
        relevant_keywords=["sha-256", "hash", "deduplication", "storage"],
        evidence="Document uploads compute a hexadecimal SHA-256 content hash to deduplicate binary payloads before streaming to storage/uploads.",
        expected_answer="SHA‑256 hash is used to detect duplicate uploads.",
        category="standard",
    ),
    # Failure case 1: lexical gap – exact identifier not recovered by vector search
    BenchmarkQuery(
        id="f1",
        query="What is the exact constant name for the negative RAG response?",
        expected_doc="rag_constants.md",
        relevant_keywords=["I do not have enough information in the provided documents to answer this question"],
        evidence="The constant NEGATIVE_RESPONSE is defined as \"I do not have enough information in the provided documents to answer this question.\"",
        expected_answer="I do not have enough information in the provided documents to answer this question.",
        category="lexical_gap",
    ),
    # Failure case 2: boundary split – answer spans two chunks
    BenchmarkQuery(
        id="f2",
        query="Describe the two‑step process of document ingestion in DevPilot.",
        expected_doc="ingestion_flow.md",
        relevant_keywords=["extract", "chunk", "store", "metadata"],
        evidence="First, text is extracted from the uploaded file. Then, the extracted text is chunked into overlapping windows before being stored.",
        expected_answer="Extraction followed by chunking and storage.",
        category="boundary_split",
    ),
    # Failure case 3: unanswerable – out‑of‑scope query
    BenchmarkQuery(
        id="f3",
        query="Can DevPilot generate JavaScript front‑end code?",
        expected_doc="",
        relevant_keywords=[],
        evidence="",
        expected_answer="",
        category="unanswerable",
    ),
]



def compute_recall_at_k(retrieved_items: list[str], ground_truth: str, k: int) -> float:
    """Compute Recall@k for a single query.
    
    Returns 1.0 if the ground_truth item is present in the top-k retrieved items, else 0.0.
    """
    if k <= 0:
        return 0.0
    top_k_items = retrieved_items[:k]
    return 1.0 if ground_truth in top_k_items else 0.0


def compute_reciprocal_rank(retrieved_items: list[str], ground_truth: str) -> float:
    """Compute Reciprocal Rank (1/rank) for a single query.
    
    Rank is 1-indexed. If not found in retrieved items, returns 0.0.
    """
    for index, item in enumerate(retrieved_items, start=1):
        if item == ground_truth:
            return 1.0 / index
    return 0.0


def compute_mrr(rankings: list[Optional[int]]) -> float:
    """Calculate Mean Reciprocal Rank across a collection of rank positions.
    
    Args:
        rankings: List of 1-based ranks where the target document was retrieved, or None.
        
    Returns:
        Mean Reciprocal Rank float value between 0.0 and 1.0.
    """
    if not rankings:
        return 0.0

    total_reciprocal_rank = sum(
        (1.0 / rank) if (rank is not None and rank > 0) else 0.0
        for rank in rankings
    )
    return total_reciprocal_rank / len(rankings)


@dataclass
class BenchmarkResult:
    """Aggregated evaluation metrics for a benchmark run."""

    queries_evaluated: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    query_details: list[dict[str, Any]] = field(default_factory=list)


class BenchmarkRunner:
    """Runner to evaluate retrieval performance over benchmark datasets."""

    def __init__(self, dataset: Optional[list[BenchmarkQuery]] = None) -> None:
        self.dataset = dataset if dataset is not None else DEFAULT_BENCHMARK_DATASET

    @staticmethod
    def evaluate_static_predictions(
        predictions: list[dict[str, Any]],
    ) -> BenchmarkResult:
        """Evaluate pre-computed retrieval predictions.
        
        Each prediction dict must contain:
            - 'retrieved': list[str] (e.g. filenames or chunk ids in ranked order)
            - 'expected': str (target identifier)
        """
        if not predictions:
            return BenchmarkResult(
                queries_evaluated=0,
                recall_at_1=0.0,
                recall_at_3=0.0,
                recall_at_5=0.0,
                mrr=0.0,
                query_details=[],
            )

        n = len(predictions)
        r1_sum = 0.0
        r3_sum = 0.0
        r5_sum = 0.0
        mrr_sum = 0.0
        details = []

        for item in predictions:
            retrieved = item.get("retrieved", [])
            expected = item.get("expected", "")

            r1 = compute_recall_at_k(retrieved, expected, k=1)
            r3 = compute_recall_at_k(retrieved, expected, k=3)
            r5 = compute_recall_at_k(retrieved, expected, k=5)
            rr = compute_reciprocal_rank(retrieved, expected)

            r1_sum += r1
            r3_sum += r3
            r5_sum += r5
            mrr_sum += rr

            # Determine 1-based rank if present
            rank = None
            if expected in retrieved:
                rank = retrieved.index(expected) + 1

            details.append({
                "expected": expected,
                "retrieved": retrieved,
                "rank": rank,
                "recall@1": r1,
                "recall@3": r3,
                "recall@5": r5,
                "reciprocal_rank": rr,
            })

        return BenchmarkResult(
            queries_evaluated=n,
            recall_at_1=round(r1_sum / n, 4),
            recall_at_3=round(r3_sum / n, 4),
            recall_at_5=round(r5_sum / n, 4),
            mrr=round(mrr_sum / n, 4),
            query_details=details,
        )

    async def run(
        self,
        retriever_fn: Callable[[str, int], Awaitable[list[str]]],
        top_k: int = 5,
    ) -> BenchmarkResult:
        """Run benchmark using an asynchronous retriever function.
        
        Args:
            retriever_fn: Async callable taking (query: str, top_k: int) and returning list of doc identifiers.
            top_k: Number of items to retrieve per query.
        """
        predictions = []
        for item in self.dataset:
            retrieved = await retriever_fn(item.query, top_k)
            predictions.append({
                "retrieved": retrieved,
                "expected": item.expected_doc,
                "query": item.query,
            })

        return self.evaluate_static_predictions(predictions)

    async def compare_retrieval_modes(
        self,
        keyword_retriever: Callable[[str, int], Awaitable[list[str]]],
        vector_retriever: Callable[[str, int], Awaitable[list[str]]],
        top_k: int = 5,
    ) -> dict[str, BenchmarkResult]:
        """Compare keyword and vector retrieval modes.

        Returns a dictionary with keys 'keyword' and 'vector' mapping to BenchmarkResult objects.
        """
        results: dict[str, BenchmarkResult] = {}

        # Keyword mode evaluation
        keyword_predictions = []
        for q in self.dataset:
            retrieved = await keyword_retriever(q.query, top_k)
            keyword_predictions.append({"retrieved": retrieved, "expected": q.expected_doc})
        results["keyword"] = self.evaluate_static_predictions(keyword_predictions)

        # Vector mode evaluation
        vector_predictions = []
        for q in self.dataset:
            retrieved = await vector_retriever(q.query, top_k)
            vector_predictions.append({"retrieved": retrieved, "expected": q.expected_doc})
        results["vector"] = self.evaluate_static_predictions(vector_predictions)
        return results
