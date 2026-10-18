"""RAG API endpoints for grounded answer synthesis and citation verification."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.search import compute_cosine_similarity
from src.core.database import get_db
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.project import Project
from src.schemas.rag import Citation, RagQueryRequest, RagResponse
from src.services.embedding import get_embedding_service
from src.services.llm import get_llm_service

router = APIRouter()


@router.post(
    "/{project_id}/rag",
    response_model=RagResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate grounded answer with citations from project documents",
)
async def generate_rag_answer(
    project_id: UUID,
    request: RagQueryRequest,
    db: AsyncSession = Depends(get_db),
) -> RagResponse:
    """Perform semantic retrieval, assemble grounded context, and synthesize an answer with citations."""
    # 1. Verify project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID '{project_id}' does not exist.",
        )

    # 2. Generate query embedding
    embedding_service = get_embedding_service()
    query_vector = await embedding_service.generate_query_embedding(request.query)

    # 3. Retrieve chunks belonging to project joined with Document for filename
    stmt = (
        select(DocumentChunk, Document.filename)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.project_id == project_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 4. Rank chunks by cosine similarity
    scored_rows: list[tuple[DocumentChunk, str, float]] = []
    for chunk, filename in rows:
        chunk_embedding = chunk.embedding or []
        score = compute_cosine_similarity(query_vector, chunk_embedding)
        scored_rows.append((chunk, filename, score))

    scored_rows.sort(key=lambda item: item[2], reverse=True)
    top_rows = scored_rows[: request.top_k]

    # 5. Format context excerpts with 1-based citation indices [1], [2], ...
    context_chunks: list[dict] = []
    for idx, (chunk, filename, score) in enumerate(top_rows, start=1):
        context_chunks.append({
            "index": idx,
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "filename": filename,
            "content": chunk.content,
            "start_offset": chunk.start_offset,
            "end_offset": chunk.end_offset,
            "score": score,
        })

    # 6. Call LLM service to generate grounded answer
    llm_service = get_llm_service()
    answer, cited_chunks = await llm_service.generate_grounded_answer(
        query=request.query,
        context_chunks=context_chunks,
        temperature=request.temperature,
    )

    # 7. Map cited chunks to Citation models
    citations: list[Citation] = []
    for c in cited_chunks:
        citations.append(
            Citation(
                citation_id=c.get("index", 1),
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                filename=c["filename"],
                start_offset=c["start_offset"],
                end_offset=c["end_offset"],
            )
        )

    return RagResponse(
        query=request.query,
        answer=answer,
        citations=citations,
        chunks_evaluated=len(context_chunks),
    )
