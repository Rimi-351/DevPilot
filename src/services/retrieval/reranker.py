"""Cross-encoder reranking service for deep semantic relevance scoring."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
DEFAULT_BLEND_RRF_WEIGHT = 0.2

# Unicode range for Bengali script (\u0980-\u09ff)
BENGALI_SCRIPT_PATTERN = re.compile(r"[\u0980-\u09ff]")


def has_bengali_script(text: str) -> bool:
    """Return True if text contains native Bengali script characters (Unicode \\u0980-\\u09ff)."""
    if not text:
        return False
    return bool(BENGALI_SCRIPT_PATTERN.search(text))


class RerankerService:
    """Cross-encoder reranking service scoring (query, chunk_text) pairs with script-aware routing."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        force_fallback: bool = False,
        enable_script_bypass: bool | None = None,
        blend_rrf_weight: float | None = None,
    ) -> None:

        from src.core.config import settings

        self.model_name = (
            model_name
            if model_name is not None
            else getattr(settings, "RERANKER_MODEL", DEFAULT_CROSS_ENCODER_MODEL)
        )
        self.device = device
        self._model = None
        self._model_failed = force_fallback
        self.enable_script_bypass = (
            enable_script_bypass
            if enable_script_bypass is not None
            else getattr(settings, "RERANKER_ENABLE_SCRIPT_BYPASS", False)
        )
        self.blend_rrf_weight = (
            blend_rrf_weight
            if blend_rrf_weight is not None
            else getattr(settings, "RERANKER_BLEND_RRF_WEIGHT", DEFAULT_BLEND_RRF_WEIGHT)
        )




    def is_monolingual_english_model(self) -> bool:
        """Check if the configured cross-encoder model is a monolingual English checkpoint."""
        model_lower = self.model_name.lower()
        if any(m in model_lower for m in ("multilingual", "mmarco", "xlm", "bge-reranker")):
            return False
        return "ms-marco" in model_lower or "en" in model_lower

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
        except Exception as exc:  # noqa: BLE001
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
        """Predict cross-encoder scores for (query, chunk_text) pairs with script-aware guardrail.

        Args:
            query: The user query string.
            candidates: List of candidate chunk dictionaries containing 'content'.
            top_k: Number of highest-ranked candidates to return.

        Returns:
            List of candidate dictionaries sorted descending by 'rerank_score', trimmed to top_k.
        """
        if not candidates:
            return []

        # Script-aware dynamic routing: If query contains native Bengali script
        # and current model is a monolingual English cross-encoder (e.g. ms-marco)
        # with bypass explicitly enabled, bypass cross-encoder to preserve Hybrid RRF order.
        # Under Approach B (Multilingual Cross-Encoder), this guardrail is disabled
        # so that native Bengali queries undergo full multilingual cross-attention.
        if (
            self.enable_script_bypass
            and has_bengali_script(query)
            and self.is_monolingual_english_model()
        ):
            logger.info(
                "SCRIPT_AWARE_RERANKER: Bengali script detected in query. "
                "Bypassing monolingual cross-encoder '%s' to preserve Hybrid RRF order.",
                self.model_name,
            )
            # Ensure candidates are ordered by rrf_score descending
            sorted_candidates = sorted(
                candidates,
                key=lambda c: float(c.get("rrf_score", 0.0)),
                reverse=True,
            )
            reranked: list[dict[str, Any]] = []
            for rank_idx, candidate in enumerate(sorted_candidates[:top_k]):
                item = dict(candidate)
                item["rerank_score"] = float(item.get("rrf_score") or (1.0 / (rank_idx + 1)))
                item["reranker_applied"] = True
                item["reranker_engine"] = "script_aware_bypass"
                reranked.append(item)
            return reranked


        # Prepare (query, passage) pairs
        pairs = [(query, c.get("content", "")) for c in candidates]

        model = self._get_model()
        scores: list[float] = []
        engine = "cross_encoder"

        if model is not None:
            try:
                raw_scores = model.predict(pairs)
                scores = [float(s) for s in raw_scores]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cross-encoder prediction error: %s. Falling back to heuristic.", exc)

                model = None

        if not scores:
            logger.warning("RERANKER_FALLBACK_ACTIVE")
            engine = "heuristic"
            # Fallback heuristic: token overlap & position weighting + previous score if any
            query_tokens = set(query.lower().split())
            for c in candidates:
                content = c.get("content", "").lower()
                overlap = sum(1 for t in query_tokens if t in content)
                existing_score = c.get("rrf_score") or c.get("score") or c.get("bm25_score") or 0.0
                heuristic_score = float(overlap * 1.5 + float(existing_score))
                scores.append(heuristic_score)

        # Optional RRF-blending: blend cross-encoder sigmoid probability with normalized RRF score
        if self.blend_rrf_weight > 0.0 and engine == "cross_encoder" and len(scores) > 1:
            import math

            def _sigmoid(x: float) -> float:
                return 1.0 / (1.0 + math.exp(-max(min(x, 20.0), -20.0)))

            sig_scores = [_sigmoid(s) for s in scores]
            rrf_raw = [float(c.get("rrf_score", 0.0)) for c in candidates]
            min_rrf, max_rrf = min(rrf_raw), max(rrf_raw)
            denom = max_rrf - min_rrf if max_rrf > min_rrf else 1.0
            norm_rrf = [(r - min_rrf) / denom for r in rrf_raw]

            blended_scores = [
                (1.0 - self.blend_rrf_weight) * sig + self.blend_rrf_weight * rrf
                for sig, rrf in zip(sig_scores, norm_rrf)
            ]
            scores = blended_scores
            engine = f"{engine}_rrf_blended"

        # Attach rerank_score and reranker metadata to each candidate
        reranked: list[dict[str, Any]] = []
        for candidate, score in zip(candidates, scores):
            item = dict(candidate)
            item["rerank_score"] = float(score)
            item["reranker_applied"] = True
            item["reranker_engine"] = engine
            reranked.append(item)

        # Sort descending by rerank_score
        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]


_default_reranker: RerankerService | None = None


def get_reranker_service() -> RerankerService:
    """Return singleton instance of RerankerService configured from application settings."""
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = RerankerService()
    return _default_reranker

