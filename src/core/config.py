"""Core configuration settings using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and environment variable definitions."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Project metadata
    PROJECT_NAME: str = "DevPilot"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # Database configuration (SQLAlchemy 2.0 async)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/devpilot",
        description="Async database connection string",
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # Ingestion & Chunking Settings
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".md", ".txt", ".py"]

    # LLM & RAG Configuration
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-oss-20b"
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Multilingual Vector Embedding Configuration
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIMENSIONS: int = 384

    # Multilingual Cross-Encoder Reranker Configuration
    RERANKER_MODEL: str = Field(
        default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        description="Cross-encoder model for semantic reranking (e.g. cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 or cross-encoder/ms-marco-MiniLM-L-6-v2)",
    )
    RERANKER_ENABLE_SCRIPT_BYPASS: bool = Field(
        default=False,
        description="Enable script-aware bypass to Hybrid RRF on monolingual models for native Bengali script",
    )
    RERANKER_BLEND_RRF_WEIGHT: float = Field(
        default=0.2,
        description="Weight of normalized Hybrid RRF consensus blended into cross-encoder sigmoid probability",
    )

    # Demo Mode & Evaluation Credentials
    DEMO_MODE: bool = Field(
        default=True,
        description="Enable read-only demo evaluation mode",
    )
    DEMO_API_KEY: str = Field(
        default="demo-readonly-key",
        description="Dedicated API key granting read-only demo evaluation access",
    )




@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


settings = get_settings()
