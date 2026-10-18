import asyncio
import sys
import os
from pathlib import Path
# Add project root to PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.core.database import engine
from src.models.base import Base
# Ensure all model modules are imported so their metadata is registered
from src.models.project import Project  # noqa: F401
from src.models.document import Document  # noqa: F401
from src.models.document_chunk import DocumentChunk  # noqa: F401
from src.models.processing_job import ProcessingJob  # noqa: F401

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created (or already existed).")

if __name__ == "__main__":
    asyncio.run(init_db())
