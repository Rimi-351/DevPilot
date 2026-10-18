"""Cross-encoder reranking service for deep semantic relevance scoring."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RerankerService:
    """Cross-encoder reranking service scoring (query, chunk_text) pairs."""

    def __init__(
        self,
        model_name: str = DEFAULT_CROSS_ENCODER_MODEL,
        device: Optional[str] = None,
        force_fallback: bool = False,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None
        self._model_failed = force_fallback

    def _get_model(self):
        """Lazy load the CrossEncoder model."""
        if self._model is not None:
            return self._model
        if self._model_failed:
            return None

        try:
            from sentence_transformers import CrossEncoder

            logger.info("Loading CrossEncoder model: %s", self.model_name)
            self._model = CrossEncoder(self.model_name, device=self.device)
            return self._model
        except Exception as exc:
            logger.warning(
                "Could not initialize CrossEncoder model '%s' (%s). Using fallback reranking heuristic.",
                self.model_name,
                exc,
            )
            self._model_failed = True
            return None

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Predict cross-encoder scores for (query, chunk_text) pairs.

        Args:
            query: The user query string.
            candidates: List of candidate chunk dictionaries containing 'content'.
            top_k: Number of highest-ranked candidates to return.

        Returns:
            List of candidate dictionaries sorted descending by 'rerank_score', trimmed to top_k.
        """
        if not candidates:
            return []

        # Prepare (query, passage) pairs
        pairs = [(query, c.get("content", "")) for c in candidates]

        model = self._get_model()
        scores: list[float] = []

        if model is not None:
            try:
                raw_scores = model.predict(pairs)
                scores = [float(s) for s in raw_scores]
            except Exception as exc:
                logger.warning("Cross-encoder prediction error: %s. Falling back to heuristic.", exc)
                model = None

        if not scores:
            # Fallback heuristic: token overlap & position weighting + previous score if any
            query_tokens = set(query.lower().split())
            for c in candidates:
                content = c.get("content", "").lower()
                overlap = sum(1 for t in query_tokens if t in content)
                existing_score = c.get("rrf_score") or c.get("score") or c.get("bm25_score") or 0.0
                heuristic_score = float(overlap * 1.5 + float(existing_score))
                scores.append(heuristic_score)

        # Attach rerank_score to each candidate
        reranked: list[dict[str, Any]] = []
        for candidate, score in zip(candidates, scores):
            item = dict(candidate)
            item["rerank_score"] = float(score)
            reranked.append(item)

        # Sort descending by rerank_score
        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]


_default_reranker: Optional[RerankerService] = None


def get_reranker_service() -> RerankerService:
    """Return singleton instance of RerankerService."""
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = RerankerService()
    return _default_reranker
