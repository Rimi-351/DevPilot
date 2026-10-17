"""Sliding-window text chunker with character offset tracking."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TextChunk:
    """Represents a discrete text chunk with position metadata."""

    index: int
    text: str
    start_offset: int
    end_offset: int

    @property
    def content(self) -> str:
        """Alias for text for consistent chunk content access."""
        return self.text

    def to_dict(self) -> dict:
        """Convert chunk metadata to dictionary."""
        return asdict(self)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[TextChunk]:
    """Partition text into overlapping segments using a sliding window.

    Args:
        text: The source string to be chunked.
        chunk_size: Maximum character length per chunk (default 500).
        chunk_overlap: Number of overlapping characters between consecutive chunks (default 50).

    Returns:
        List of TextChunk instances with index, text, start_offset, and end_offset.

    Raises:
        ValueError: If chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap cannot be negative, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be strictly less than chunk_size ({chunk_size})"
        )

    if not text:
        return []

    text_length = len(text)
    step = chunk_size - chunk_overlap
    chunks: list[TextChunk] = []

    start_offset = 0
    chunk_index = 0

    while start_offset < text_length:
        end_offset = min(start_offset + chunk_size, text_length)
        chunk_content = text[start_offset:end_offset]

        chunks.append(
            TextChunk(
                index=chunk_index,
                text=chunk_content,
                start_offset=start_offset,
                end_offset=end_offset,
            )
        )

        chunk_index += 1
        if end_offset >= text_length:
            break
        start_offset += step

    return chunks
