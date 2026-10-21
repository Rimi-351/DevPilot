"""Anti-hallucination and citation verification guardrails for grounded RAG synthesis."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from src.evaluation.metrics import compute_unsupported_claims_rate
from src.services.llm import NEGATIVE_RESPONSE

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Structured result of citation verification and anti-hallucination guardrail evaluation."""

    cleaned_answer: str
    raw_answer: str
    valid_citations: list[dict[str, Any]] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    citation_correctness: float = 1.0
    unsupported_claims_rate: float = 0.0
    is_grounded: bool = True


class CitationVerificationService:
    """Validates citations in generated answers against retrieved context chunks, strips

    hallucinated/invented citation markers, and computes grounding metrics.
    """

    def __init__(self, max_unsupported_threshold: float = 0.20) -> None:
        self.max_unsupported_threshold = max_unsupported_threshold

    def verify_and_filter_citations(
        self,
        raw_answer: str,
        context_chunks: list[dict[str, Any]],
        strip_invalid: bool = True,
        flag_ungrounded: bool = True,
    ) -> VerificationResult:
        """Verify all citations in raw_answer against context_chunks.

        Args:
            raw_answer: Generated LLM response text containing citations like [1], [2], or [chunk: ...].
            context_chunks: List of retrieved context chunk dictionaries containing:
                - index (1-based integer)
                - chunk_id (UUID or str)
                - document_id (UUID or str)
                - filename (str)
                - content (str)
            strip_invalid: Whether to strip invalid/hallucinated citations from the returned answer.
            flag_ungrounded: Whether to flag the response with is_grounded=False if invalid citations
                             or unsupported claims are detected.

        Returns:
            VerificationResult containing cleaned answer, valid chunk citations, stripped invalid
            citations, citation correctness score, unsupported claims rate, and is_grounded boolean.
        """
        if not raw_answer or not raw_answer.strip():
            return VerificationResult(
                cleaned_answer=raw_answer,
                raw_answer=raw_answer,
                valid_citations=[],
                invalid_citations=[],
                citation_correctness=1.0,
                unsupported_claims_rate=0.0,
                is_grounded=True,
            )

        # Standard polite rejection responses are always grounded with no citations
        if NEGATIVE_RESPONSE.lower() in raw_answer.lower():
            return VerificationResult(
                cleaned_answer=NEGATIVE_RESPONSE,
                raw_answer=raw_answer,
                valid_citations=[],
                invalid_citations=[],
                citation_correctness=1.0,
                unsupported_claims_rate=0.0,
                is_grounded=True,
            )

        # Build index maps for fast validation
        valid_indices: dict[int, dict[str, Any]] = {}
        valid_chunk_ids: dict[str, dict[str, Any]] = {}
        valid_doc_ids: dict[str, dict[str, Any]] = {}

        for idx, chunk in enumerate(context_chunks, start=1):
            index_num = chunk.get("index", idx)
            valid_indices[int(index_num)] = chunk

            c_id = chunk.get("chunk_id")
            if c_id:
                valid_chunk_ids[str(c_id).lower()] = chunk

            d_id = chunk.get("document_id")
            if d_id:
                valid_doc_ids[str(d_id).lower()] = chunk

        # Normalize special unicode brackets (e.g. Japanese/Chinese full-width 【1】 -> [1])
        text = raw_answer.replace("\u2011", "-")
        text = re.sub(r"[【](\d+)[】]", r"[\1]", text)

        invalid_citations: list[str] = []
        valid_chunk_matches: list[dict[str, Any]] = []
        seen_valid_chunk_ids: set[Any] = set()

        # Step 1: Detect and process UUID-based citations: [chunk: <uuid>], [doc: <uuid>], or [<uuid>]
        uuid_pattern = re.compile(
            r"\[(?:chunk|doc|document|ref|source)?[:\s_-]*([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\]",
            re.IGNORECASE,
        )

        def replace_uuid_citation(match: re.Match[str]) -> str:
            raw_tag = match.group(0)
            uuid_str = match.group(1).lower()

            matched_chunk = valid_chunk_ids.get(uuid_str) or valid_doc_ids.get(uuid_str)
            if matched_chunk:
                c_id = matched_chunk.get("chunk_id")
                if c_id is not None and c_id not in seen_valid_chunk_ids:
                    seen_valid_chunk_ids.add(c_id)
                    valid_chunk_matches.append(matched_chunk)
                # Normalize to standard 1-based bracket [index]
                idx_num = matched_chunk.get("index", 1)
                return f"[{idx_num}]"
            else:
                invalid_citations.append(raw_tag)
                return "" if strip_invalid else raw_tag

        text = uuid_pattern.sub(replace_uuid_citation, text)

        # Step 2: Detect and process custom named/invented tags: e.g. [chunk: fake-id-123], [ref: ungrounded]
        named_pattern = re.compile(
            r"\[(?:chunk|doc|document|ref|source)[:\s_-]+([^\]]+)\]",
            re.IGNORECASE,
        )

        def replace_named_citation(match: re.Match[str]) -> str:
            raw_tag = match.group(0)
            tag_val = match.group(1).strip().lower()

            matched_chunk = valid_chunk_ids.get(tag_val) or valid_doc_ids.get(tag_val)
            if matched_chunk:
                c_id = matched_chunk.get("chunk_id")
                if c_id is not None and c_id not in seen_valid_chunk_ids:
                    seen_valid_chunk_ids.add(c_id)
                    valid_chunk_matches.append(matched_chunk)
                return f"[{matched_chunk.get('index', 1)}]"
            else:
                invalid_citations.append(raw_tag)
                return "" if strip_invalid else raw_tag

        text = named_pattern.sub(replace_named_citation, text)

        # Step 3: Detect and process numeric bracket citations: [1], [99], [1, 2], [1, 99]
        numeric_pattern = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

        def replace_numeric_citation(match: re.Match[str]) -> str:
            raw_tag = match.group(0)
            numbers: list[int] = []
            for n in match.group(1).split(","):
                cleaned_n = n.strip()
                if cleaned_n.isdigit():
                    try:
                        numbers.append(int(cleaned_n))
                    except (ValueError, OverflowError):
                        continue

            valid_nums: list[int] = []
            for num in numbers:
                if num in valid_indices:
                    valid_nums.append(num)
                    chunk = valid_indices[num]
                    c_id = chunk.get("chunk_id")
                    if c_id is not None and c_id not in seen_valid_chunk_ids:
                        seen_valid_chunk_ids.add(c_id)
                        valid_chunk_matches.append(chunk)
                else:
                    invalid_citations.append(f"[{num}]")

            if not strip_invalid:
                return raw_tag

            if valid_nums:
                return f"[{', '.join(str(n) for n in valid_nums)}]"
            return ""

        text = numeric_pattern.sub(replace_numeric_citation, text)

        # Step 4: Text cleanup after stripping
        cleaned_answer = text
        if strip_invalid:
            # Clean spaces before punctuation (e.g. "fact ." -> "fact.")
            cleaned_answer = re.sub(r" +([.,!?;])", r"\1", cleaned_answer)
            # Collapse multiple spaces
            cleaned_answer = re.sub(r" +", " ", cleaned_answer)
            # Remove empty brackets or dangling punctuation
            cleaned_answer = re.sub(r"\[\s*\]", "", cleaned_answer)
            cleaned_answer = cleaned_answer.strip()

        # Step 5: Metrics computation
        total_raw_citations = len(valid_chunk_matches) + len(invalid_citations)
        if total_raw_citations == 0:
            citation_correctness = 1.0
        else:
            citation_correctness = round(len(valid_chunk_matches) / total_raw_citations, 4)

        # Calculate unsupported claims rate against retrieved context chunks
        unsupported_claims_rate = compute_unsupported_claims_rate(
            answer=cleaned_answer,
            retrieved_chunks=context_chunks,
        )

        # Grounding status determination
        has_invalid = len(invalid_citations) > 0
        has_unsupported_claims = unsupported_claims_rate > self.max_unsupported_threshold
        is_grounded = not (has_invalid or has_unsupported_claims)

        if not is_grounded:
            logger.warning(
                "Citation guardrail detected ungrounded response: "
                "invalid_citations=%s, unsupported_claims_rate=%.2f, citation_correctness=%.2f",
                invalid_citations,
                unsupported_claims_rate,
                citation_correctness,
            )

        return VerificationResult(
            cleaned_answer=cleaned_answer,
            raw_answer=raw_answer,
            valid_citations=valid_chunk_matches,
            invalid_citations=invalid_citations,
            citation_correctness=citation_correctness,
            unsupported_claims_rate=unsupported_claims_rate,
            is_grounded=is_grounded,
        )


_default_guardrail_service: Optional[CitationVerificationService] = None


def get_citation_verification_service() -> CitationVerificationService:
    """Return singleton instance of CitationVerificationService."""
    global _default_guardrail_service
    if _default_guardrail_service is None:
        _default_guardrail_service = CitationVerificationService()
    return _default_guardrail_service


__all__ = [
    "CitationVerificationService",
    "VerificationResult",
    "get_citation_verification_service",
]
