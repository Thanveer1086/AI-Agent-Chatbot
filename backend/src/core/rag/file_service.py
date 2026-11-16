"""File Ingestion Service with Transactional Rollback."""
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from src.core.db.session import db_manager
from src.core.db.blob import storage_client
from src.core.rag.ingest import doc_parser
from src.core.rag.media_ingest import parse_csv_to_chunks
from src.core.rag.embeddings import get_embedding

logger = logging.getLogger(__name__)

async def process_and_index_file(
    file_bytes: bytes,
    filename: str,
    application_ids: List[int],
    document_type_id: int = 1,
    category_ids: List[int] = None,
    uploaded_by: str = "system"
) -> Tuple[bool, str, Dict[str, Any]]:
    """Process file, generate embeddings, store blob, and index chunks with rollback safety."""
    if category_ids is None:
        category_ids = []

    # 1. Stage file temporarily
    staging_dir = Path("./storage/staging")
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_path = staging_dir / filename
    temp_path.write_bytes(file_bytes)

    inserted_file_id = None
    storage_url = None

    try:
        # 2. Parse file into chunks
        ext = temp_path.suffix.lower()
        if ext in [".csv", ".tsv"]:
            chunks = parse_csv_to_chunks(temp_path, filename)
        else:
            md_text = doc_parser.parse_to_markdown(temp_path, filename)
            chunks = doc_parser.chunk_markdown(md_text, filename)

        if not chunks:
            return False, "File parsing produced no indexable text chunks.", {}

        # 3. Resolve Application Names for filtering
        async with db_manager.acquire() as conn:
            app_rows = await conn.fetch("SELECT name FROM applications WHERE id = ANY($1)", application_ids)
            app_names = [r["name"] for r in app_rows] if app_rows else ["General Knowledge"]

        # 4. Upload original file to Object Storage
        storage_url = await storage_client.upload(filename, file_bytes)

        # 5. Generate embeddings concurrently in parallel batches (10x faster)
        sem = asyncio.Semaphore(10)
        async def embed_single(c):
            async with sem:
                vec = await get_embedding(c["chunk_text"])
                return c, vec

        embed_tasks = [embed_single(c) for c in chunks]
        embedded_chunks = await asyncio.gather(*embed_tasks)

        # 6. Insert metadata and vector chunks in a single PostgreSQL transaction
        async with db_manager.acquire() as conn:
            async with conn.transaction():
                # Insert uploaded_files record
                row = await conn.fetchrow("""
                    INSERT INTO uploaded_files 
                        (filename, file_size, mime_type, storage_url, application_ids, category_ids, document_type_id, indexed_chunks, is_enabled, uploaded_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE, $9)
                    RETURNING id;
                """, filename, len(file_bytes), ext, storage_url, application_ids, category_ids, document_type_id, len(chunks), uploaded_by)
                inserted_file_id = row["id"]

                # Insert primary_vector_chunks
                for c, dense_vec in embedded_chunks:
                    vec_str = "[" + ",".join(f"{x:.6f}" for x in dense_vec) + "]"

                    await conn.execute("""
                        INSERT INTO primary_vector_chunks
                            (file_id, filename, chunk_index, chunk_text, section_title, dense_vector, application_names, category_ids, document_type_id, is_enabled)
                        VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, $9, TRUE);
                    """, inserted_file_id, filename, c["chunk_index"], c["chunk_text"], c.get("section_title"), vec_str, app_names, category_ids, document_type_id)

        logger.info(f"Successfully processed and indexed '{filename}': {len(chunks)} chunks.")
        return True, "File indexed successfully.", {
            "file_id": inserted_file_id,
            "filename": filename,
            "indexed_chunks": len(chunks),
            "storage_url": storage_url
        }

    except Exception as e:
        logger.error(f"Error indexing file {filename}: {e}. Initiating compensation rollback...")
        # Rollback storage
        if storage_url:
            await storage_client.delete(filename)
        # Rollback DB if partial rows created
        if inserted_file_id:
            try:
                async with db_manager.acquire() as conn:
                    await conn.execute("DELETE FROM uploaded_files WHERE id = $1", inserted_file_id)
            except Exception as rollback_err:
                logger.error(f"DB rollback failure: {rollback_err}")

        return False, f"Failed to process file: {str(e)}", {}

    finally:
        # Clean up staged temporary file
        if temp_path.exists():
            temp_path.unlink()
