"""Vector index bookkeeping: which embedding model built the stored vectors, and re-indexing.

Vectors from different embedding models cannot be compared. The `embedding_index_meta`
table records the provider/model/dimension that produced the stored vectors. If the
configured provider differs, dense (vector) search is switched off (keyword search
still works) and uploads are refused until `reindex_all()` re-embeds everything.
"""
import logging
import time
from typing import Any, Dict, List, Optional

from src.config import settings
from src.core.db.session import db_manager
from src.core.rag.embeddings import get_embeddings, vector_literal

logger = logging.getLogger(__name__)

REINDEX_COMMAND = "docker compose exec backend python -m src.scripts.reindex_embeddings"

# Cached result of the last check, used on the hot search/upload paths
_state: Dict[str, Any] = {"compatible": True, "checked": False, "reason": None}

VECTOR_TABLES = {
    "primary_vector_chunks": ("idx_vector_chunks_hnsw", "WITH (m = 16, ef_construction = 64)"),
    "approved_answers": ("idx_approved_answers_hnsw", ""),
}


def current_identity() -> Dict[str, Any]:
    return {
        "provider": settings.EMBEDDING_PROVIDER,
        "model": settings.embedding_model_name,
        "dimension": settings.EXPECTED_EMBEDDING_DIM,
    }


def is_index_compatible() -> bool:
    return bool(_state["compatible"])


def incompatibility_reason() -> Optional[str]:
    return _state["reason"]


async def _column_dims(conn) -> Dict[str, Optional[int]]:
    rows = await conn.fetch(
        """
        SELECT c.relname AS table_name, a.atttypmod AS dims
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relname = ANY($1::text[]) AND a.attname = 'dense_vector' AND NOT a.attisdropped;
        """,
        list(VECTOR_TABLES),
    )
    return {r["table_name"]: r["dims"] for r in rows}


async def _row_counts(conn) -> Dict[str, int]:
    return {t: await conn.fetchval(f"SELECT count(*) FROM {t}") for t in VECTOR_TABLES}


async def _get_meta(conn) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow("SELECT provider, model, dimension FROM embedding_index_meta WHERE id = 1")
    return dict(row) if row else None


async def _set_meta(conn) -> None:
    ident = current_identity()
    await conn.execute(
        """
        INSERT INTO embedding_index_meta (id, provider, model, dimension, updated_at)
        VALUES (1, $1, $2, $3, NOW())
        ON CONFLICT (id) DO UPDATE SET provider = EXCLUDED.provider, model = EXCLUDED.model,
            dimension = EXCLUDED.dimension, updated_at = NOW();
        """,
        ident["provider"], ident["model"], ident["dimension"],
    )


async def _set_column_dims(conn, dims: int) -> None:
    """Change the vector columns to `dims` (only safe when the columns hold no data or are being rewritten)."""
    for table, (index, options) in VECTOR_TABLES.items():
        await conn.execute(f"DROP INDEX IF EXISTS {index};")
        await conn.execute(f"ALTER TABLE {table} ALTER COLUMN dense_vector DROP NOT NULL;")
        await conn.execute(f"UPDATE {table} SET dense_vector = NULL;")
        await conn.execute(f"ALTER TABLE {table} ALTER COLUMN dense_vector TYPE vector({dims});")


async def _restore_constraints(conn) -> None:
    for table, (index, options) in VECTOR_TABLES.items():
        await conn.execute(f"ALTER TABLE {table} ALTER COLUMN dense_vector SET NOT NULL;")
        await conn.execute(
            f"CREATE INDEX IF NOT EXISTS {index} ON {table} USING hnsw (dense_vector vector_cosine_ops) {options};"
        )


async def check_index() -> Dict[str, Any]:
    """Compare stored vectors with the configured provider; auto-fix an empty index."""
    ident = current_identity()
    async with db_manager.acquire() as conn:
        dims = await _column_dims(conn)
        counts = await _row_counts(conn)
        meta = await _get_meta(conn)
        empty = all(c == 0 for c in counts.values())
        dims_ok = all(d == ident["dimension"] for d in dims.values())

        if empty and (not dims_ok or meta != ident):
            # Nothing stored yet: safe to adopt the configured provider immediately.
            async with conn.transaction():
                if not dims_ok:
                    await _set_column_dims(conn, ident["dimension"])
                    await _restore_constraints(conn)
                await _set_meta(conn)
            logger.info(f"Empty vector index prepared for {ident}.")
            meta, dims_ok = ident, True

    if not dims_ok:
        reason = (f"Vector columns are {sorted(set(dims.values()))}-dimensional but "
                  f"EXPECTED_EMBEDDING_DIM={ident['dimension']}.")
    elif meta is None:
        reason = "Stored vectors were created before model tracking existed (model unknown)."
    elif meta != ident:
        reason = f"Stored vectors were made with {meta['provider']}/{meta['model']} ({meta['dimension']}d)."
    else:
        reason = None

    _state.update({"compatible": reason is None, "checked": True, "reason": reason})
    status = {
        "configured": ident,
        "stored": meta,
        "column_dimensions": dims,
        "rows": counts,
        "compatible": reason is None,
        "reason": reason,
    }
    if reason:
        logger.warning(
            f"EMBEDDING INDEX MISMATCH: {reason} Vector search is disabled (keyword search still works) "
            f"and uploads are paused. Re-embed everything with:\n    {REINDEX_COMMAND}"
        )
    return status


async def reindex_all() -> Dict[str, Any]:
    """Re-embed every chunk and approved answer with the configured provider.

    New vectors are computed first; the database is only changed afterwards, inside one
    transaction, so a failure part-way leaves the existing index untouched.
    """
    started = time.time()
    ident = current_identity()
    async with db_manager.acquire() as conn:
        chunks = await conn.fetch("SELECT id, chunk_text FROM primary_vector_chunks ORDER BY id;")
        answers = await conn.fetch("SELECT id, question_text FROM approved_answers ORDER BY id;")

    logger.info(f"Re-indexing {len(chunks)} chunks and {len(answers)} approved answers with {ident}...")
    chunk_vectors: List[List[float]] = await get_embeddings([r["chunk_text"] for r in chunks], is_query=False)
    # Approved-answer questions are matched against user questions, so they embed as queries
    answer_vectors: List[List[float]] = await get_embeddings([r["question_text"] for r in answers], is_query=True)

    async with db_manager.acquire() as conn:
        async with conn.transaction():
            await _set_column_dims(conn, ident["dimension"])
            await conn.executemany(
                "UPDATE primary_vector_chunks SET dense_vector = $2::vector WHERE id = $1;",
                [(r["id"], vector_literal(v)) for r, v in zip(chunks, chunk_vectors)],
            )
            await conn.executemany(
                "UPDATE approved_answers SET dense_vector = $2::vector WHERE id = $1;",
                [(r["id"], vector_literal(v)) for r, v in zip(answers, answer_vectors)],
            )
            await _restore_constraints(conn)
            await _set_meta(conn)

    _state.update({"compatible": True, "checked": True, "reason": None})
    result = {
        "provider": ident["provider"],
        "model": ident["model"],
        "dimension": ident["dimension"],
        "chunks": len(chunks),
        "approved_answers": len(answers),
        "seconds": round(time.time() - started, 1),
    }
    logger.info(f"Re-index complete: {result}")
    return result


async def ensure_meta_for_new_index() -> None:
    """Record the provider the first time vectors are written to an index without metadata."""
    async with db_manager.acquire() as conn:
        if await _get_meta(conn) is None:
            await _set_meta(conn)
