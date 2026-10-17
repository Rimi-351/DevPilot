"""Integration tests for document ingestion, storage, extraction, and chunking."""

import io
import uuid
import pytest
from httpx import AsyncClient
from pypdf import PdfWriter

from src.core.config import settings
from src.services.chunker import chunk_text


# --- Chunker Unit & Boundary Tests ---


def test_chunking_boundaries_and_overlap() -> None:
    """Verify sliding-window chunking logic, boundary offsets, and overlap continuity."""
    # Construct a string of known length (1200 characters)
    text = "A" * 450 + "B" * 50 + "C" * 450 + "D" * 50 + "E" * 200  # 1200 chars
    chunk_size = 500
    chunk_overlap = 50

    chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    assert len(chunks) == 3

    # Chunk 0
    assert chunks[0].index == 0
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == 500
    assert len(chunks[0].text) == 500

    # Chunk 1: Starts at 500 - 50 = 450
    assert chunks[1].index == 1
    assert chunks[1].start_offset == 450
    assert chunks[1].end_offset == 950
    assert len(chunks[1].text) == 500

    # Chunk 2: Starts at 950 - 50 = 900
    assert chunks[2].index == 2
    assert chunks[2].start_offset == 900
    assert chunks[2].end_offset == 1200
    assert len(chunks[2].text) == 300

    # Overlap verification: last 50 chars of Chunk 0 must equal first 50 chars of Chunk 1
    overlap_0_1 = chunks[0].text[-chunk_overlap:]
    assert overlap_0_1 == chunks[1].text[:chunk_overlap]
    assert overlap_0_1 == "B" * 50


def test_chunking_edge_cases() -> None:
    """Verify empty text, small text, and invalid argument handling."""
    # Empty string
    assert chunk_text("") == []

    # Text shorter than chunk_size
    short_text = "Short text content."
    single = chunk_text(short_text, chunk_size=500, chunk_overlap=50)
    assert len(single) == 1
    assert single[0].text == short_text
    assert single[0].start_offset == 0
    assert single[0].end_offset == len(short_text)

    # Invalid arguments
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        chunk_text("abc", chunk_size=0)

    with pytest.raises(ValueError, match="chunk_overlap cannot be negative"):
        chunk_text("abc", chunk_size=100, chunk_overlap=-5)

    with pytest.raises(ValueError, match="strictly less than chunk_size"):
        chunk_text("abc", chunk_size=100, chunk_overlap=100)


# --- Ingestion Pipeline API Integration Tests ---


@pytest.mark.asyncio
async def test_upload_text_file_and_background_processing(client: AsyncClient) -> None:
    """Verify text file upload, storage, document record creation, and background chunking completion."""
    # 1. Create project
    proj_res = await client.post("/api/v1/projects", json={"name": "Ingestion Project"})
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 2. Upload text document
    file_content = b"# Architecture Overview\n\n" + (b"DevPilot asynchronous backend processing.\n" * 30)
    files = {
        "file": ("architecture.md", file_content, "text/markdown"),
    }
    data = {
        "project_id": project_id,
    }

    upload_res = await client.post("/api/v1/documents/upload", data=data, files=files)
    assert upload_res.status_code == 201
    doc_data = upload_res.json()

    assert doc_data["filename"] == "architecture.md"
    assert doc_data["project_id"] == project_id
    assert "job_id" in doc_data
    assert doc_data["file_size_bytes"] == len(file_content)

    job_id = doc_data["job_id"]

    # 3. Retrieve background ProcessingJob status
    job_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()

    assert job_data["status"] == "COMPLETED"
    assert job_data["result"] is not None
    assert job_data["result"]["chunk_count"] >= 1
    assert job_data["result"]["total_characters"] == len(file_content.decode("utf-8"))


@pytest.mark.asyncio
async def test_upload_pdf_file_and_background_processing(client: AsyncClient) -> None:
    """Verify PDF upload, extraction via pypdf, and background chunking completion."""
    proj_res = await client.post("/api/v1/projects", json={"name": "PDF Project"})
    project_id = proj_res.json()["id"]

    # Create a valid minimal PDF in-memory
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    files = {
        "file": ("specification.pdf", pdf_bytes, "application/pdf"),
    }
    data = {
        "project_id": project_id,
    }

    upload_res = await client.post("/api/v1/documents/upload", data=data, files=files)
    assert upload_res.status_code == 201
    doc_data = upload_res.json()

    job_id = doc_data["job_id"]
    job_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that files exceeding the maximum size limit are rejected with HTTP 413."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Oversized Test"})
    project_id = proj_res.json()["id"]

    # Temporarily set max upload size to 100 bytes for test
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 100)

    oversized_content = b"X" * 150  # 150 bytes > 100 bytes
    files = {
        "file": ("large_file.txt", oversized_content, "text/plain"),
    }
    data = {
        "project_id": project_id,
    }

    upload_res = await client.post("/api/v1/documents/upload", data=data, files=files)
    assert upload_res.status_code == 413
    assert "exceeds the maximum allowed limit" in upload_res.json()["detail"]


@pytest.mark.asyncio
async def test_upload_unsupported_extension_rejected(client: AsyncClient) -> None:
    """Verify that files with unsupported extensions are rejected with HTTP 400."""
    proj_res = await client.post("/api/v1/projects", json={"name": "Unsupported Ext Test"})
    project_id = proj_res.json()["id"]

    files = {
        "file": ("malicious_payload.exe", b"binary content", "application/octet-stream"),
    }
    data = {
        "project_id": project_id,
    }

    upload_res = await client.post("/api/v1/documents/upload", data=data, files=files)
    assert upload_res.status_code == 400
    assert "is not supported" in upload_res.json()["detail"]


@pytest.mark.asyncio
async def test_upload_nonexistent_project_rejected(client: AsyncClient) -> None:
    """Verify that uploading to a non-existent project returns HTTP 404."""
    random_id = str(uuid.uuid4())
    files = {
        "file": ("document.txt", b"some text", "text/plain"),
    }
    data = {
        "project_id": random_id,
    }

    upload_res = await client.post("/api/v1/documents/upload", data=data, files=files)
    assert upload_res.status_code == 404
