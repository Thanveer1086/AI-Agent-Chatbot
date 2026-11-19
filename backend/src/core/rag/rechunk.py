"""Rebuild the chunks of already-uploaded documents from their stored original files.

Used after changing the chunking rules: no re-upload is needed. For each file the new
chunks and embeddings are prepared first; the old chunks are then replaced inside one
transaction, so a failure leaves that file's existing chunks untouched. Each file keeps
its enabled/disabled state, applications, categories and document type.
"""
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from src.core.db.blob import storage_client
from src.core.db.session import db_manager
from src.core.rag.embeddings import get_embeddings, vector_literal
from src.core.rag.file_service import STAGING_DIR, build_chunks
from src.core.rag.index_admin import ensure_meta_for_new_index, incompatibility_reason, is_index_compatible

logger = logging.getLogger(__name__)


async def rechunk_file(file_row) -> Dict[str, Any]:
    file_id, filename = file_row["id"], file_row["filename"]
    key = storage_client.key_from_storage_url(file_row["storage_url"])
    data = await storage_client.download(key)
    if data is None:
        raise FileNotFoundError(f"original file '{key}' is missing from storage")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = STAGING_DIR / f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
    temp_path.write_bytes(data)
    try:
        chunks = build_chunks(temp_path, filename)
    finally:
        temp_path.unlink(missing_ok=True)
    if not chunks:
        raise ValueError("parsing produced no chunks")

    vectors = await get_embeddings([c["chunk_text"] for c in chunks])

    async with db_manager.acquire() as conn:
        app_rows = await conn.fetch(
            "SELECT name FROM applications WHERE id = ANY($1::int[])", list(file_row["application_ids"] or [])
        )
        app_names = [r["name"] for r in app_rows] or ["General Knowledge"]
        async with conn.transaction():
            old_count = await conn.fetchval("SELECT count(*) FROM primary_vector_chunks WHERE file_id = $1", file_id)
            await conn.execute("DELETE FROM primary_vector_chunks WHERE file_id = $1", file_id)
            await conn.executemany(
                """
                INSERT INTO primary_vector_chunks
                    (file_id, filename, chunk_index, chunk_text, section_title, dense_vector,
                     application_names, category_ids, document_type_id, is_enabled)
                VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, $9, $10);
                """,
                [
                    (file_id, filename, c["chunk_index"], c["chunk_text"], c.get("section_title"),
                     vector_literal(v), app_names, list(file_row["category_ids"] or []),
                     file_row["document_type_id"], file_row["is_enabled"])
                    for c, v in zip(chunks, vectors)
                ],
            )
            await conn.execute(
                "UPDATE uploaded_files SET indexed_chunks = $2, updated_at = NOW() WHERE id = $1",
                file_id, len(chunks),
            )
    return {"file_id": file_id, "filename": filename, "old_chunks": old_count, "new_chunks": len(chunks),
            "enabled": file_row["is_enabled"]}


async def rechunk_all() -> Dict[str, Any]:
    if not is_index_compatible():
        raise RuntimeError(f"Embedding index mismatch ({incompatibility_reason()}); run the re-index first.")

    started = time.time()
    async with db_manager.acquire() as conn:
        files = await conn.fetch(
            "SELECT id, filename, storage_url, application_ids, category_ids, document_type_id, is_enabled "
            "FROM uploaded_files ORDER BY id"
        )

    done: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for row in files:
        try:
            result = await rechunk_file(row)
            done.append(result)
            logger.info(f"Re-chunked {result}")
        except Exception as e:
            logger.error(f"Re-chunk failed for '{row['filename']}': {e} (its old chunks were kept)")
            failed.append({"file_id": row["id"], "filename": row["filename"], "error": str(e)})

    await ensure_meta_for_new_index()
    return {"files": done, "failed": failed, "seconds": round(time.time() - started, 1)}
