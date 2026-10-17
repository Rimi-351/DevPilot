"""Text extraction service supporting Text, Markdown, Python, and PDF files."""

import io
from pathlib import Path
from typing import Optional

import aiofiles
from pypdf import PdfReader


async def extract_text_from_file(
    file_path: str | Path,
    file_type: Optional[str] = None,
) -> str:
    """Extract full textual content from local file path based on extension and mime type."""
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".pdf" or (file_type and "pdf" in file_type.lower()):
        return await _extract_text_from_pdf(path)

    # Plain text, markdown, source code files (.py, .txt, .md, etc.)
    return await _extract_text_from_plaintext(path)


async def _extract_text_from_plaintext(path: Path) -> str:
    """Read plain text or code file with utf-8 decoding."""
    async with aiofiles.open(path, mode="r", encoding="utf-8", errors="replace") as f:
        return await f.read()


async def _extract_text_from_pdf(path: Path) -> str:
    """Extract text from all pages of a PDF document using pypdf."""
    async with aiofiles.open(path, mode="rb") as f:
        pdf_bytes = await f.read()

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_texts: list[str] = []
    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            page_texts.append(text.strip())

    return "\n\n".join(page_texts)
