"""Core configuration settings using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

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

    # Ingestion & Storage Settings
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".md", ".txt", ".py"]

    # LLM & RAG Configuration
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-oss-20b"
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


settings = get_settings()
