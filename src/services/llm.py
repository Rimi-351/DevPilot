"""Grounded LLM service for context-synthesized answers and source citations."""

import os
import re
from typing import Optional

import httpx
from fastapi import HTTPException

from src.core.config import settings

NEGATIVE_RESPONSE = (
    "I do not have enough information in the provided documents to answer this question."
)

SYSTEM_PROMPT = """You are DevPilot AI, a strictly grounded technical assistant.
You answer user questions SOLELY using the provided context excerpts labeled as [1], [2], etc.

Rules:
1. Answer the question using ONLY facts directly mentioned in the provided excerpts.
2. Every factual statement or claim MUST include a citation marker like [1] or [2] corresponding to the excerpt used.
3. If the excerpts do not contain enough information to answer the question, you must respond EXACTLY with:
"I do not have enough information in the provided documents to answer this question."
4. Do NOT speculate, hallucinate, extrapolate, or bring in external knowledge."""

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "should", "shouldn't", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "won't", "would", "wouldn't", "you", "your",
    "yours", "yourself", "yourselves", "tell", "give", "explain", "describe",
}


class LLMService:
    """Asynchronous LLM service for generating strictly grounded RAG responses with citations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        force_mock: Optional[bool] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.model = model if model is not None else settings.LLM_MODEL
        self.base_url = base_url if base_url is not None else settings.LLM_BASE_URL

        # Determine whether to use mock based on environment or key availability
        if force_mock is not None:
            self._use_mock = force_mock
        else:
            self._use_mock = (
                not self.api_key
                or self.api_key.lower() in ("mock", "test", "")
                or os.getenv("TESTING", "").lower() in ("1", "true")
                or "PYTEST_CURRENT_TEST" in os.environ
                or os.getenv("LLM_MOCK", "").lower() in ("1", "true")
            )

    def _generate_mock_answer(
        self,
        query: str,
        context_chunks: list[dict],
    ) -> tuple[str, list[dict]]:
        """Generate a deterministic grounded answer or negative rejection using keyword overlap."""
        if not context_chunks:
            return NEGATIVE_RESPONSE, []

        cleaned_query = query.strip().lower()
        query_tokens = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", cleaned_query)
        keywords = [t for t in query_tokens if t not in STOPWORDS and len(t) >= 3]
        if not keywords:
            keywords = query_tokens

        matched_chunks_with_scores: list[tuple[dict, list[str], int]] = []
        for chunk in context_chunks:
            content = chunk.get("content", "")
            content_lower = content.lower()
            matched_kws = [kw for kw in keywords if kw in content_lower]
            if matched_kws:
                matched_chunks_with_scores.append((chunk, matched_kws, len(matched_kws)))

        if not matched_chunks_with_scores:
            return NEGATIVE_RESPONSE, []

        # Sort by match count descending, then by chunk index
        matched_chunks_with_scores.sort(
            key=lambda item: (item[2], -item[0].get("index", 1)),
            reverse=True,
        )

        grounded_parts: list[str] = []
        cited_chunks: list[dict] = []

        for chunk, matched_kws, _ in matched_chunks_with_scores:
            idx = chunk.get("index", 1)
            content = chunk.get("content", "").strip()

            # Split sentences cleanly
            sentences = re.split(r"(?<=[.!?])\s+", content)
            relevant_sentences = [
                s.strip()
                for s in sentences
                if any(kw in s.lower() for kw in matched_kws) and len(s.strip()) > 3
            ]

            if relevant_sentences:
                excerpt = " ".join(relevant_sentences[:2])
            else:
                excerpt = sentences[0].strip() if sentences else content[:120].strip()

            # Ensure excerpt ends cleanly
            if not excerpt.endswith((".", "!", "?")):
                excerpt += "."

            grounded_parts.append(f"{excerpt} [{idx}]")
            cited_chunks.append(chunk)

        answer = " ".join(grounded_parts)
        return answer, cited_chunks

    async def generate_grounded_answer(
        self,
        query: str,
        context_chunks: list[dict],
        temperature: float = 0.0,
    ) -> tuple[str, list[dict]]:
        """Generate a grounded answer and extract citations from retrieved chunks."""
        if not context_chunks:
            return NEGATIVE_RESPONSE, []

        if self._use_mock:
            return self._generate_mock_answer(query, context_chunks)

        # Real LLM API execution via httpx
        context_texts = []
        for chunk in context_chunks:
            idx = chunk.get("index", 1)
            filename = chunk.get("filename", "document")
            content = chunk.get("content", "")
            context_texts.append(f"[{idx}] (File: {filename}):\n{content}")

        context_str = "\n\n".join(context_texts)
        user_prompt = f"Context Excerpts:\n{context_str}\n\nQuestion: {query}\n\nAnswer:"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                # Handle specific HTTP error statuses
                if res.status_code == 401:
                    raise HTTPException(status_code=502, detail="External LLM authentication failed - verify LLM_API_KEY")
                if res.status_code == 429:
                    raise HTTPException(status_code=502, detail="External LLM rate limit or quota exceeded - check balance/tier")
                res.raise_for_status()
                data = res.json()
                answer = data["choices"][0]["message"]["content"].strip()
        except httpx.RequestError as e:
            # Network or timeout errors
            raise HTTPException(status_code=504, detail="External LLM request failed - check connectivity or timeout") from e
        except HTTPException:
            # Propagate HTTPException upwards
            raise
        except Exception:
            # Fallback to mock on unexpected errors
            return self._generate_mock_answer(query, context_chunks)

        if NEGATIVE_RESPONSE.lower() in answer.lower():
            return NEGATIVE_RESPONSE, []

        # Normalize non-breaking hyphens and full-width citation brackets (e.g. 【1】 -> [1])
        answer = answer.replace("\u2011", "-")
        answer = re.sub(r"[【](\d+)[】]", r"[\1]", answer)

        # Parse citation indices e.g. [1], [2]
        citation_indices = sorted(list(set(int(m) for m in re.findall(r"\[(\d+)\]", answer))))
        chunk_by_idx = {c.get("index", i + 1): c for i, c in enumerate(context_chunks)}
        cited_chunks = [chunk_by_idx[i] for i in citation_indices if i in chunk_by_idx]

        return answer, cited_chunks


_default_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return singleton instance of LLMService."""
    global _default_llm_service
    if _default_llm_service is None:
        _default_llm_service = LLMService()
    return _default_llm_service
