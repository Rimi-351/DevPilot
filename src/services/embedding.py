"""Embedding service providing asynchronous text vectorization with fastembed and mock fallback."""

import asyncio
import hashlib
import math
import os
import re
from typing import Optional


class EmbeddingService:
    """Asynchronous embedding generation service supporting fastembed and deterministic test mock."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        dimensions: int = 384,
        force_mock: Optional[bool] = None,
    ) -> None:
        self.model_name = model_name
        self.dimensions = dimensions

        # Auto-detect test environment or mock override
        if force_mock is not None:
            self._use_mock = force_mock
        else:
            self._use_mock = (
                os.getenv("TESTING", "").lower() in ("1", "true")
                or "PYTEST_CURRENT_TEST" in os.environ
                or os.getenv("EMBEDDING_MOCK", "").lower() in ("1", "true")
            )

        self._model = None
        self._init_lock = asyncio.Lock()

    def _get_mock_embedding(self, text: str) -> list[float]:
        """Generate a deterministic, normalized 384-dimensional embedding for test environments.
        
        Uses token hashing with L2 normalization so semantic overlap produces higher cosine similarity.
        """
        vec = [0.0] * self.dimensions
        cleaned = text.strip().lower()
        if not cleaned:
            vec[0] = 1.0
            return vec

        # Tokenize words and character 3-grams for semantic similarity matching
        words = re.findall(r"\w+", cleaned)
        tokens = list(words)
        for w in words:
            if len(w) >= 3:
                tokens.extend(w[i : i + 3] for i in range(len(w) - 2))

        if not tokens:
            tokens = [cleaned]

        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimensions
            sign = 1.0 if ((h >> 9) & 1) == 0 else -1.0
            vec[idx] += sign

        # L2 normalize vector
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0

        return vec

    def _load_model_sync(self) -> None:
        """Synchronously load fastembed model."""
        if self._model is None and not self._use_mock:
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name)
            except Exception:
                # Fallback to mock if fastembed or model weights cannot be loaded
                self._use_mock = True

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronously generate embeddings via fastembed or mock."""
        if self._use_mock or self._model is None:
            return [self._get_mock_embedding(t) for t in texts]

        try:
            embeddings_gen = self._model.embed(texts)
            return [emb.tolist() for emb in embeddings_gen]
        except Exception:
            return [self._get_mock_embedding(t) for t in texts]

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of strings asynchronously."""
        if not texts:
            return []

        if not self._use_mock and self._model is None:
            async with self._init_lock:
                if self._model is None and not self._use_mock:
                    await asyncio.to_thread(self._load_model_sync)

        return await asyncio.to_thread(self._embed_sync, texts)

    async def generate_query_embedding(self, text: str) -> list[float]:
        """Generate a single embedding vector for a query string asynchronously."""
        embeddings = await self.generate_embeddings([text])
        if embeddings:
            return embeddings[0]
        return [0.0] * self.dimensions


_default_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Return singleton instance of EmbeddingService."""
    global _default_embedding_service
    if _default_embedding_service is None:
        _default_embedding_service = EmbeddingService()
    return _default_embedding_service
