"""Hybrid Search Query Engine (Dense Vector + BM25 Sparse Lexical)."""
import logging
from typing import List, Dict, Any, Optional
from src.core.db.session import db_manager
from src.core.rag.embeddings import get_embedding
from src.config import settings

logger = logging.getLogger(__name__)

async def search_dense_vectors(
    query: str,
    application_name: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Retrieve top-K candidates using cosine similarity over pgvector HNSW index."""
    query_vector = await get_embedding(query)
    vector_str = "[" + ",".join(f"{x:.6f}" for x in query_vector) + "]"

    sql = """
        SELECT 
            id::text as chunk_id,
            filename,
            chunk_index,
            chunk_text,
            section_title,
            1 - (dense_vector <=> $1::vector) as similarity_score
        FROM primary_vector_chunks
        WHERE is_enabled = TRUE
          AND $2 = ANY(application_names)
        ORDER BY dense_vector <=> $1::vector ASC
        LIMIT $3;
    """
    async with db_manager.acquire() as conn:
        try:
            rows = await conn.fetch(sql, vector_str, application_name, limit)
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "filename": row["filename"],
                    "chunk_index": row["chunk_index"],
                    "chunk_text": row["chunk_text"],
                    "section_title": row["section_title"],
                    "score": float(row["similarity_score"]),
                    "retrieval_type": "dense"
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Dense vector search failed: {e}")
            return []

async def search_bm25_lexical(
    query: str,
    application_name: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Retrieve top-K candidates using full-text TSVECTOR search."""
    cleaned_query = " | ".join(word for word in query.split() if len(word) > 2)
    if not cleaned_query:
        cleaned_query = query

    sql = """
        SELECT 
            id::text as chunk_id,
            filename,
            chunk_index,
            chunk_text,
            section_title,
            ts_rank(sparse_tokens, to_tsquery('english', $1)) as bm25_rank
        FROM primary_vector_chunks
        WHERE is_enabled = TRUE
          AND $2 = ANY(application_names)
          AND sparse_tokens @@ to_tsquery('english', $1)
        ORDER BY bm25_rank DESC
        LIMIT $3;
    """
    async with db_manager.acquire() as conn:
        try:
            rows = await conn.fetch(sql, cleaned_query, application_name, limit)
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "filename": row["filename"],
                    "chunk_index": row["chunk_index"],
                    "chunk_text": row["chunk_text"],
                    "section_title": row["section_title"],
                    "score": float(row["bm25_rank"]),
                    "retrieval_type": "bm25"
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"BM25 search skipped or query format issue ({cleaned_query}): {e}")
            return []
