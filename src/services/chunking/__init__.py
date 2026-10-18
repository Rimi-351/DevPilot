"""Text chunking service package with sliding-window segmentation."""

from src.services.chunker import TextChunk, chunk_text

__all__ = ["TextChunk", "chunk_text"]
