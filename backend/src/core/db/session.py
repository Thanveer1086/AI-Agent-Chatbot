"""Database session and asyncpg connection pool manager."""
import asyncpg
import logging
from pathlib import Path
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
from src.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Initialize the asyncpg connection pool and run initial schema migrations."""
        if self._pool is not None:
            return

        logger.info("Initializing asyncpg connection pool...")
        try:
            self._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=settings.DB_POOL_MIN,
                max_size=settings.DB_POOL_MAX,
                command_timeout=60,
            )
            logger.info("Database pool established successfully.")
            await self.init_schema()
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise e

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            logger.info("Closing asyncpg database connection pool...")
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed.")

    async def init_schema(self) -> None:
        """Execute schema.sql to ensure tables and indexes exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            logger.warning(f"Schema file not found at {schema_path}")
            return

        sql = schema_path.read_text(encoding="utf-8")
        async with self.acquire() as conn:
            try:
                await conn.execute(sql)
                logger.info("Database schema and extensions initialized.")
            except Exception as e:
                logger.warning(f"Schema init notice (table or extension already configured): {e}")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Acquire a connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database pool is not initialized. Call connect() first.")
        async with self._pool.acquire() as connection:
            yield connection

db_manager = DatabaseManager()

async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Dependency helper for FastAPI endpoints."""
    async with db_manager.acquire() as conn:
        yield conn
