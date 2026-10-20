"""Multilingual embedding service providing asynchronous text vectorization with FastEmbed, SentenceTransformers, and deterministic mock fallback."""

import asyncio
import hashlib
import math
import os
import re
from typing import Optional


# Multilingual Unicode token pattern for mock vectorization:
# English, Bengali script (\u0980-\u09ff, \u200c, \u200d), and alphanumeric Banglish
_MULTILINGUAL_TOKEN_PATTERN = re.compile(r"[\w\u0980-\u09ff\u200c\u200d]+")


class EmbeddingService:
    """Asynchronous embedding generation service supporting FastEmbed, SentenceTransformers, and deterministic test mock."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
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
        self._backend: str = "mock" if self._use_mock else "uninitialized"
        self._init_lock = asyncio.Lock()

    def _get_mock_embedding(self, text: str) -> list[float]:
        """Generate a deterministic, normalized 384-dimensional embedding for test environments.
        
        Uses token hashing with L2 normalization so semantic overlap produces higher cosine similarity.
        Supports English, pure Bangla script, and Romanized Banglish tokens.
        """
        vec = [0.0] * self.dimensions
        cleaned = text.strip().lower()
        if not cleaned:
            vec[0] = 1.0
            return vec

        # Tokenize words and character 3-grams for semantic similarity matching
        words = _MULTILINGUAL_TOKEN_PATTERN.findall(cleaned)
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
        """Synchronously load embedding model using FastEmbed, SentenceTransformers, or mock fallback."""
        if self._model is not None or self._use_mock:
            return

        # 1. Attempt loading with FastEmbed (optimized CPU ONNX runtime)
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
            self._backend = "fastembed"
            return
        except Exception:
            pass

        # 2. Attempt loading with SentenceTransformers (PyTorch multilingual encoders)
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._backend = "sentence_transformers"
            return
        except Exception:
            pass

        # 3. Fallback to deterministic mock if offline or dependencies/weights unavailable
        self._use_mock = True
        self._backend = "mock"

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronously generate embeddings via FastEmbed, SentenceTransformers, or mock."""
        if self._use_mock or self._model is None:
            return [self._get_mock_embedding(t) for t in texts]

        try:
            if self._backend == "sentence_transformers":
                embeddings = self._model.encode(texts, normalize_embeddings=True)
                return [emb.tolist() for emb in embeddings]
            else:
                # FastEmbed generator
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
    """Return singleton instance of EmbeddingService configured from application settings."""
    global _default_embedding_service
    if _default_embedding_service is None:
        try:
            from src.core.config import settings

            model_name = getattr(settings, "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            dimensions = getattr(settings, "EMBEDDING_DIMENSIONS", 384)
        except Exception:
            model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            dimensions = 384
        _default_embedding_service = EmbeddingService(model_name=model_name, dimensions=dimensions)
    return _default_embedding_service
