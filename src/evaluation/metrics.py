"""Information retrieval, generation, and multilingual evaluation metrics for DevPilot."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence


def compute_hit_at_k(retrieved_ids: Sequence[Any], ground_truth_ids: set[Any]) -> float:
    """Compute binary Hit@k: 1.0 if at least one ground-truth ID is in retrieved_ids, else 0.0."""
    return 1.0 if any(r_id in ground_truth_ids for r_id in retrieved_ids) else 0.0


def compute_recall_at_k(
    retrieved_chunk_ids: Sequence[Any],
    ground_truth_chunk_ids: Sequence[Any] | Any,
    k: int = 5,
) -> float:
    """Computes Recall@k: 1.0 if at least one ground-truth chunk is in the top-k retrieved chunks, else 0.0.

    Supports both list of ground truth IDs and single ground truth string identifier.
    """
    if k <= 0 or not ground_truth_chunk_ids or not retrieved_chunk_ids:
        return 0.0

    top_k_retrieved = set(retrieved_chunk_ids[:k])
    if isinstance(ground_truth_chunk_ids, (str, bytes)):
        gt_set = {ground_truth_chunk_ids}
    else:
        gt_set = set(ground_truth_chunk_ids)

    # Intersection check
    return 1.0 if not top_k_retrieved.isdisjoint(gt_set) else 0.0


def compute_reciprocal_rank(
    retrieved_ids: Sequence[Any],
    ground_truth_ids: set[Any] | str,
) -> float:
    """Compute Reciprocal Rank: 1 / rank of the first matching ground-truth item, or 0.0.

    Rank is 1-indexed. Supports ground_truth_ids as a set/collection or single string.
    """
    if not retrieved_ids or not ground_truth_ids:
        return 0.0

    if isinstance(ground_truth_ids, (str, bytes)):
        gt_set = {ground_truth_ids}
    else:
        gt_set = set(ground_truth_ids)

    for rank_idx, r_id in enumerate(retrieved_ids, start=1):
        if r_id in gt_set:
            return 1.0 / rank_idx
    return 0.0


def compute_mrr(
    retrieved_chunk_ids: Sequence[Any] | list[float],
    ground_truth_chunk_ids: Sequence[Any] | None = None,
) -> float:
    """Computes Mean Reciprocal Rank (MRR).

    Supported calling conventions for full backward and cross-module compatibility:
      1. compute_mrr(retrieved_chunk_ids, ground_truth_chunk_ids):
         Calculates the reciprocal rank (1.0 / rank) of the first matching chunk in
         retrieved_chunk_ids that is present in ground_truth_chunk_ids (or 0.0 if none match).
      2. compute_mrr(reciprocal_ranks):
         Computes the arithmetic mean over a precomputed list of reciprocal rank scores.
    """
    if ground_truth_chunk_ids is not None:
        if not ground_truth_chunk_ids or not retrieved_chunk_ids:
            return 0.0

        gt_set = set(ground_truth_chunk_ids)
        for rank, chunk_id in enumerate(retrieved_chunk_ids, start=1):
            if chunk_id in gt_set:
                return 1.0 / rank

        return 0.0

    # 1-argument mode: precomputed sequence of reciprocal rank numbers
    if not retrieved_chunk_ids:
        return 0.0
    return float(sum(retrieved_chunk_ids) / len(retrieved_chunk_ids))


def evaluate_multilingual_run(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates metrics globally and across language slices (English, Bangla, Banglish)."""
    metrics_by_lang: Dict[str, List[Dict[str, float]]] = {}
    global_recall_5: list[float] = []
    global_mrr: list[float] = []

    for item in results:
        lang = item.get("language", "english")
        retrieved = item.get("retrieved_chunk_ids", [])
        gt = item.get("ground_truth_chunk_ids", [])

        r5 = compute_recall_at_k(retrieved, gt, k=5)
        mrr = compute_mrr(retrieved, gt)

        global_recall_5.append(r5)
        global_mrr.append(mrr)

        if lang not in metrics_by_lang:
            metrics_by_lang[lang] = []
        metrics_by_lang[lang].append({"recall_at_5": r5, "mrr": mrr})

    summary: dict[str, Any] = {
        "global_recall_at_5": sum(global_recall_5) / len(global_recall_5) if global_recall_5 else 0.0,
        "global_mrr": sum(global_mrr) / len(global_mrr) if global_mrr else 0.0,
        "languages": {},
    }

    for lang, scores in metrics_by_lang.items():
        r5_list = [s["recall_at_5"] for s in scores]
        mrr_list = [s["mrr"] for s in scores]
        summary["languages"][lang] = {
            "count": len(scores),
            "recall_at_5": sum(r5_list) / len(r5_list),
            "mrr": sum(mrr_list) / len(mrr_list),
        }

    return summary


def compute_unsupported_claims_rate(
    answer: str,
    retrieved_chunks: list[dict[str, Any]],
    overlap_threshold: float = 0.40,
) -> float:
    """Calculate the unsupported claims rate for a generated answer.

    Definition:
        The percentage of generated claim sentences citing or referencing context chunks
        where the sentence-to-chunk token overlap ratio is strictly less than the threshold (0.40).

    Formula:
        For each claim sentence S:
            overlap_ratio(S, C) = |tokens(S) ∩ tokens(C)| / |tokens(S)|
            A claim sentence S is classified as unsupported if:
                max_{C}(overlap_ratio(S, C)) < overlap_threshold (0.40)
        unsupported_claims_rate = count(unsupported_sentences) / total_claim_sentences

    Args:
        answer: The synthesized answer text generated by the LLM.
        retrieved_chunks: List of retrieved context chunk dictionaries containing 'content'.
        overlap_threshold: Minimum sentence-to-chunk token overlap ratio required to classify
                           a claim as supported (default: 0.40).

    Returns:
        Float between 0.0 (all claim sentences supported by retrieved chunks) and 1.0 (all claims unsupported).
    """
    from src.services.llm import STOPWORDS

    if not answer or not answer.strip() or not retrieved_chunks:
        return 0.0

    # Negative refusals ("I do not have enough information...") are grounded negative constraints
    if "i do not have enough information" in answer.lower():
        return 0.0

    # Split answer into candidate claim sentences
    raw_sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    claim_sentences = []

    for s in raw_sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        # Extract meaningful non-stopword alphanumeric tokens
        tokens = [
            t for t in re.findall(r"\w+", s_clean.lower())
            if len(t) > 2 and t not in STOPWORDS and not t.isdigit()
        ]
        if tokens:
            claim_sentences.append((s_clean, tokens))

    if not claim_sentences:
        return 0.0

    # Build token sets for each retrieved chunk (and track indexed chunks [1], [2]...)
    chunk_token_sets = []
    chunk_by_citation_idx: dict[int, set[str]] = {}

    for idx, c in enumerate(retrieved_chunks, start=1):
        content = c.get("content", "")
        c_tokens = set(re.findall(r"\w+", content.lower()))
        chunk_token_sets.append(c_tokens)
        citation_num = c.get("index") or idx
        chunk_by_citation_idx[int(citation_num)] = c_tokens

    unsupported_count = 0

    for sentence_text, s_tokens in claim_sentences:
        s_token_set = set(s_tokens)
        s_token_count = len(s_token_set)

        # Check if sentence cites specific chunks (e.g. [1], [2])
        cited_indices = [int(m) for m in re.findall(r"\[(\d+)\]", sentence_text)]
        relevant_chunk_token_sets = [
            chunk_by_citation_idx[idx]
            for idx in cited_indices
            if idx in chunk_by_citation_idx
        ]

        # If no specific citation or cited chunk not in index, check against all retrieved chunks
        candidate_sets = relevant_chunk_token_sets if relevant_chunk_token_sets else chunk_token_sets

        # Calculate max overlap ratio across relevant chunks
        max_overlap_ratio = 0.0
        for c_set in candidate_sets:
            overlap = len(s_token_set & c_set)
            ratio = overlap / max(s_token_count, 1)
            if ratio > max_overlap_ratio:
                max_overlap_ratio = ratio

        # If max sentence-to-chunk token overlap ratio is < threshold (0.40), claim is unsupported
        if max_overlap_ratio < overlap_threshold:
            unsupported_count += 1

    return round(unsupported_count / len(claim_sentences), 4)


__all__ = [
    "compute_hit_at_k",
    "compute_recall_at_k",
    "compute_reciprocal_rank",
    "compute_mrr",
    "compute_unsupported_claims_rate",
    "evaluate_multilingual_run",
]
