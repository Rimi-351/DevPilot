"""Search service utilities for DevPilot.

Provides lexical keyword based retrieval as a lightweight baseline
and can be used alongside the vector based search endpoint.
"""

import re
from typing import List

from src.models.document_chunk import DocumentChunk


def lexical_keyword_search(query: str, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
    """Return chunks ranked by simple keyword overlap.

    The function tokenizes the query and each chunk's content into lower‑case
    word tokens (``\w+``). Overlap is measured by the count of shared tokens.
    Chunks are sorted descending by overlap score; ties are resolved by the
    original order of ``chunks``.
    """
    query_tokens = set(re.findall(r"\w+", query.lower()))
    # Compute overlap count for each chunk
    scored = []
    for chunk in chunks:
        chunk_tokens = set(re.findall(r"\w+", chunk.content.lower()))
        overlap = len(query_tokens & chunk_tokens)
        scored.append((overlap, chunk))
    # Sort by overlap descending
    scored.sort(key=lambda x: x[0], reverse=True)
    # Return only the chunk objects, preserving order
    return [c for _, c in scored]
