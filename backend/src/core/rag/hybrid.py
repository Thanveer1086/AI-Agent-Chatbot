"""Hybrid Search Query Engine (Dense Vector + BM25 Sparse Lexical)."""
import re
import logging
from typing import List, Dict, Any, Optional, Sequence
from src.core.db.session import db_manager
from src.core.rag.embeddings import vector_literal
from src.config import settings

logger = logging.getLogger(__name__)

def build_lexical_query(query: str) -> str:
    """Build a to_tsquery expression that can never be a syntax error.

    Only alphanumeric tokens survive (so "policy?", "what's" or "C++" cannot break
    the parser) and they are OR-ed for recall; ts_rank orders the matches.
    """
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", query.lower()) if len(t) > 2]
    return " | ".join(dict.fromkeys(tokens))

async def search_dense_vectors(
    query_vector: Optional[Sequence[float]],
    application_name: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Retrieve top-K candidates using cosine similarity over pgvector HNSW index."""
    if not query_vector:
        return []
    vector_str = vector_literal(query_vector)

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
    cleaned_query = build_lexical_query(query)
    if not cleaned_query:
        return []

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
