"""
Agent tools for the DevPilot bounded agentic workflow.

Each tool is a plain async function that performs exactly one well-defined
data operation and returns a structured dict ready for LLM context injection.
They accept only the arguments they genuinely need — no fat service objects —
which makes them trivially mockable in tests.

Tool  ↔  Phase mapping (enforced by the dispatcher, not here):
  search_project   →  SEARCH
  inspect_chunk    →  INSPECT
  summarize_text   →  SUMMARIZE

Design principles:
  - Raise ValueError for logical / data-not-found errors so the dispatcher
    can catch them and produce a ToolExecutionStatus.EXECUTION_ERROR log entry
    that feeds back into the LLM context without crashing the agent loop.
  - Never import from src.services.agent.schemas here; tools are schema-agnostic
    and can be exercised independently of the agent orchestration layer.
  - All DB access uses the injected AsyncSession — no hidden singleton sessions.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.services.llm import get_llm_service
from src.services.retrieval import retrieve_chunks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chunk_row_to_dict(chunk: DocumentChunk, filename: str) -> dict[str, Any]:
    """Convert a DocumentChunk ORM row into the standard chunk dict consumed
    by the retrieval pipeline and tool outputs.

    Keeps the shape identical to what ``retrieve_chunks`` returns so that
    tool outputs can be fed seamlessly into downstream pipeline steps.
    """
    return {
        "chunk_id": chunk.id,
        "document_id": chunk.document_id,
        "filename": filename,
        "content": chunk.content,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "chunk_index": chunk.chunk_index,
        "embedding": chunk.embedding or [],
    }


def _extractive_summarize(text: str, max_sentences: int = 4) -> str:
    """Lightweight extractive summariser used as a synchronous fallback when
    the LLM service is in mock mode or unavailable.

    Scores sentences by normalised term frequency of content words (words > 3
    characters) and returns the top ``max_sentences`` in their original order
    to preserve narrative coherence.

    Args:
        text:          Source text to summarise.
        max_sentences: Maximum number of sentences to retain.

    Returns:
        A condensed string of the highest-scoring sentences.
    """
    # Split on sentence boundaries while preserving the delimiter
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= max_sentences:
        return text.strip()

    # Build a normalised term-frequency table over content words
    content_word_re = re.compile(r"\b[a-zA-Z]{4,}\b")
    all_words = content_word_re.findall(text.lower())
    if not all_words:
        # No scoreable content words; return first N sentences verbatim
        return " ".join(sentences[:max_sentences])

    word_counts: dict[str, int] = {}
    for w in all_words:
        word_counts[w] = word_counts.get(w, 0) + 1
    max_freq = max(word_counts.values())
    tf: dict[str, float] = {w: c / max_freq for w, c in word_counts.items()}

    # Score each sentence by the mean TF of its content words
    scored: list[tuple[float, int, str]] = []
    for idx, sentence in enumerate(sentences):
        words = content_word_re.findall(sentence.lower())
        if not words:
            scored.append((0.0, idx, sentence))
            continue
        sentence_score = sum(tf.get(w, 0.0) for w in words) / len(words)
        scored.append((sentence_score, idx, sentence))

    # Select top sentences and restore document order
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences]
    top_ordered = sorted(top, key=lambda x: x[1])
    return " ".join(s for _, _, s in top_ordered)


# ---------------------------------------------------------------------------
# Tool 1: search_project  (SEARCH phase)
# ---------------------------------------------------------------------------

async def search_project(
    query: str,
    project_id: UUID,
    session: AsyncSession,
    *,
    search_mode: str = "hybrid",
    top_k: int = 5,
    chunk_limit: int = 20,
) -> dict[str, Any]:
    """Retrieve the most relevant document chunks for ``query`` within a project.

    Runs the full Week-5 hybrid retrieval pipeline:
      1. Dense vector similarity (EmbeddingService cosine)
      2. BM25 sparse lexical search
      3. Reciprocal Rank Fusion (RRF) to merge both ranked lists

    Args:
        query:        Natural-language search string (already validated by SearchInput).
        project_id:   UUID of the owning project; enforces multi-tenant isolation.
        session:      Active async database session (injected — never opened here).
        search_mode:  Retrieval mode forwarded to ``retrieve_chunks``.
                      Default "hybrid" (dense + BM25 + RRF).
        top_k:        Maximum number of chunks to return to the LLM context.
        chunk_limit:  Candidate pool size for initial retrieval before fusion.

    Returns:
        Dict with keys:
          ``chunks``     – list of ranked chunk dicts (chunk_id, content, filename, …)
          ``query``      – echoed query string
          ``total_found``– total candidate pool size before trimming to top_k
          ``search_mode``– mode used

    Raises:
        ValueError: If the project has no indexed chunks at all.
    """
    logger.debug(
        "search_project: query=%r project_id=%s mode=%s top_k=%d",
        query, project_id, search_mode, top_k,
    )

    # 1. Fetch all chunks belonging to this project, joined with Document for filename
    stmt = (
        select(DocumentChunk, Document.filename)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.project_id == project_id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        raise ValueError(
            f"Project '{project_id}' has no indexed document chunks. "
            "Ensure at least one document has been uploaded and processed."
        )

    # 2. Shape rows into the standard chunk dict format
    candidate_chunks: list[dict[str, Any]] = [
        _chunk_row_to_dict(chunk, filename) for chunk, filename in rows
    ]

    logger.debug(
        "search_project: %d candidate chunks fetched for project %s",
        len(candidate_chunks), project_id,
    )

    # 3. Run hybrid retrieval pipeline (dense + BM25 + RRF via retrieve_chunks)
    ranked_chunks = await retrieve_chunks(
        query=query,
        chunks=candidate_chunks,
        search_mode=search_mode,
        top_k=top_k,
        chunk_limit=chunk_limit,
    )

    # 4. Attach 1-based citation indices for downstream LLM context assembly
    for idx, chunk in enumerate(ranked_chunks, start=1):
        chunk["index"] = idx

    logger.info(
        "search_project: returned %d/%d chunks for query=%r",
        len(ranked_chunks), len(candidate_chunks), query,
    )

    return {
        "query": query,
        "chunks": ranked_chunks,
        "total_found": len(candidate_chunks),
        "search_mode": search_mode,
    }


# ---------------------------------------------------------------------------
# Tool 2: inspect_chunk  (INSPECT phase)
# ---------------------------------------------------------------------------

async def inspect_chunk(
    chunk_id: str,
    project_id: UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    """Fetch the full text content of a specific document chunk.

    Enforces project-scoped isolation: even if the caller supplies a valid
    ``chunk_id``, the chunk must belong to ``project_id``.  Cross-project
    inspection raises ValueError so the agent cannot leak tenant data.

    Args:
        chunk_id:   Chunk UUID string (UUID4 or 32-char hex, pre-validated by InspectInput).
        project_id: UUID of the owning project used to enforce tenant isolation.
        session:    Active async database session.

    Returns:
        Dict with keys:
          ``chunk_id``    – echoed identifier
          ``project_id``  – owning project UUID (str)
          ``document_id`` – parent document UUID (str)
          ``filename``    – human-readable filename of the source document
          ``content``     – full raw text of the chunk
          ``start_offset``– character offset into the source document
          ``end_offset``  – character offset (end, exclusive)
          ``chunk_index`` – 0-based position within the parent document

    Raises:
        ValueError: If the chunk does not exist or belongs to a different project.
    """
    # Normalise chunk_id: strip hyphens to get a bare hex string for UUID()
    try:
        chunk_uuid = UUID(chunk_id)
    except ValueError as exc:
        # InspectInput regex should have caught this; defensive re-raise
        raise ValueError(f"Malformed chunk_id '{chunk_id}': {exc}") from exc

    logger.debug(
        "inspect_chunk: chunk_id=%s project_id=%s", chunk_uuid, project_id
    )

    # Single compound query: chunk must match BOTH id AND project_id
    stmt = (
        select(DocumentChunk, Document.filename)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            and_(
                DocumentChunk.id == chunk_uuid,
                DocumentChunk.project_id == project_id,
            )
        )
    )
    result = await session.execute(stmt)
    row = result.first()

    if row is None:
        raise ValueError(
            f"Chunk '{chunk_id}' not found in project '{project_id}'. "
            "Verify the chunk_id is from a search_project result for this project."
        )

    chunk, filename = row

    logger.info(
        "inspect_chunk: found chunk %s (%d chars) in doc '%s'",
        chunk_uuid, len(chunk.content), filename,
    )

    return {
        "chunk_id": str(chunk.id),
        "project_id": str(chunk.project_id),
        "document_id": str(chunk.document_id),
        "filename": filename,
        "content": chunk.content,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "chunk_index": chunk.chunk_index,
    }


# ---------------------------------------------------------------------------
# Tool 3: summarize_text  (SUMMARIZE phase)
# ---------------------------------------------------------------------------

async def summarize_text(text: str) -> dict[str, Any]:
    """Distil key findings from a text excerpt into a concise multi-sentence summary.

    Strategy (ordered by availability):
      1. **LLM summarisation** — if ``LLMService`` is not in mock/test mode, a
         grounded one-shot prompt asks the model for a bullet-pointed condensation.
      2. **Extractive fallback** — if the LLM is in mock mode or returns a
         negative response, ``_extractive_summarize`` picks the highest-scoring
         sentences by normalised term frequency (no external dependencies).

    The LLM path reuses the existing ``LLMService`` singleton (same API key,
    base_url, and mock-detection logic as the RAG endpoint) so behaviour is
    consistent across the whole application.

    Args:
        text: Full chunk content to summarise (min 20 chars, pre-validated).

    Returns:
        Dict with keys:
          ``summary``             – condensed text output
          ``original_char_count`` – character length of the input
          ``summary_char_count``  – character length of the output
          ``method``              – "llm" or "extractive" indicating the path taken
    """
    logger.debug("summarize_text: input length=%d chars", len(text))

    llm_service = get_llm_service()
    summary: str = ""
    method: str = "extractive"

    if not llm_service._use_mock:
        # Construct a tight summarisation prompt — single context chunk, no citations needed
        summarisation_prompt = (
            "Produce a concise, factual summary (3-5 sentences) of the following excerpt. "
            "Focus on technical findings, key concepts, and actionable insights. "
            "Do not add information not present in the excerpt.\n\n"
            f"Excerpt:\n{text}\n\nSummary:"
        )
        try:
            # generate_grounded_answer accepts a single-chunk context list;
            # we pass the text as the sole context so it acts as a summariser
            context_chunk = [{"content": text, "index": 1, "filename": "source"}]
            raw_answer, _ = await llm_service.generate_grounded_answer(
                query=summarisation_prompt,
                context_chunks=context_chunk,
                temperature=0.0,
            )
            # Reject the negative-response sentinel — fall through to extractive
            if raw_answer and "I do not have enough information" not in raw_answer:
                summary = raw_answer.strip()
                method = "llm"
                logger.info("summarize_text: LLM path succeeded (%d chars)", len(summary))
        except Exception as exc:
            logger.warning(
                "summarize_text: LLM path failed (%s), falling back to extractive.", exc
            )

    # Extractive path — runs when LLM is in mock mode, unavailable, or returned a sentinel
    if not summary:
        summary = _extractive_summarize(text, max_sentences=4)
        method = "extractive"
        logger.info("summarize_text: extractive path used (%d chars)", len(summary))

    return {
        "summary": summary,
        "original_char_count": len(text),
        "summary_char_count": len(summary),
        "method": method,
    }
