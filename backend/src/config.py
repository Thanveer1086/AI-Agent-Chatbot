"""Application configuration and environment settings validator."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Literal, Optional
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Providers
    API_USED: Literal["openai", "gemini"] = "openai"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Embeddings
    EMBEDDING_PROVIDER: Literal["openai", "gemini"] = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    EXPECTED_EMBEDDING_DIM: int = 1536

    # Database & Storage
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/agent_chatbot"
    DB_POOL_MIN: int = Field(default=2, ge=1)
    DB_POOL_MAX: int = Field(default=10, le=50)
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
    AZURE_CONTAINER_NAME: str = "documents"
    DEV_STORAGE_LOCAL_PATH: str = "./storage/blobs"

    # Security & Auth
    DEV_AUTH_BYPASS: bool = True
    JWT_SECRET: str = "super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    # Agent Guardrails (Constitution compliant)
    MAX_AGENT_ITERATIONS: int = Field(default=5, ge=1, le=10)
    TOOL_TIMEOUT_SECONDS: int = Field(default=15, ge=1, le=60)
    RERANKING_ENABLED: bool = True
    RERANK_TOP_K: int = Field(default=5, ge=1, le=20)

    # External Tools & Integrations
    GITHUB_PAT: Optional[str] = None
    GITHUB_USERNAME: str = "Thanveer1086"

    # Retrieval parameters
    RRF_K: int = 60
    BM25_MIN_SCORE: float = 0.05
    RERANK_INITIAL_LIMIT: int = 20

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql://") and not v.startswith("postgres://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URI")
        return v

# Cached singleton
settings = Settings()
