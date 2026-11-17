"""Application configuration and environment settings validator."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Literal, Optional

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
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    # Tried in order after GEMINI_MODEL if a call fails (comma-separated)
    GEMINI_FALLBACK_MODELS: str = "gemini-3.5-flash,gemini-3.1-flash-lite"
    # Optional faster/cheaper model for the planner step; defaults to the main model
    PLANNER_MODEL: Optional[str] = None
    # Max seconds to wait for a model response (or the next streamed chunk) before failing over
    LLM_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=300)

    # Embeddings
    EMBEDDING_PROVIDER: Literal["openai", "gemini"] = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    EXPECTED_EMBEDDING_DIM: int = 1536
    # Only for offline development: store hash-based fake vectors when no key is set.
    # Keep False in real use, otherwise search quality is silently destroyed.
    ALLOW_MOCK_EMBEDDINGS: bool = False

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
    # Comma-separated list of browser origins allowed to call the API
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    MAX_UPLOAD_MB: int = Field(default=50, ge=1, le=500)

    # Agent Guardrails (Constitution compliant)
    MAX_AGENT_ITERATIONS: int = Field(default=5, ge=1, le=10)
    TOOL_TIMEOUT_SECONDS: int = Field(default=15, ge=1, le=60)
    RERANKING_ENABLED: bool = True
    # Discover MCP tools and load the reranker in the background at startup
    WARMUP_ON_STARTUP: bool = True
    RERANK_TOP_K: int = Field(default=5, ge=1, le=20)
    # Number of prior chat messages sent to the planner and answer model
    CHAT_HISTORY_MESSAGES: int = Field(default=10, ge=0, le=50)

    # External Tools & Integrations
    GITHUB_PAT: Optional[str] = None
    GITHUB_USERNAME: Optional[str] = None

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

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip() and o.strip() != "*"]

    @property
    def gemini_models(self) -> List[str]:
        models = [self.GEMINI_MODEL] + [m.strip() for m in self.GEMINI_FALLBACK_MODELS.split(",")]
        return list(dict.fromkeys(m for m in models if m))

# Cached singleton
settings = Settings()
