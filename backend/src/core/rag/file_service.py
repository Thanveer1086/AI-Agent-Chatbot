"""File Ingestion Service with Transactional Rollback."""
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from src.core.db.session import db_manager
from src.core.db.blob import storage_client
from src.core.rag.ingest import doc_parser, SUPPORTED_EXTENSIONS
from src.core.rag.media_ingest import parse_csv_to_chunks, parse_xlsx_to_chunks
from src.core.rag.embeddings import get_embeddings, vector_literal
from src.core.security.paths import safe_filename

logger = logging.getLogger(__name__)

STAGING_DIR = Path("./storage/staging")


async def process_and_index_file(
    file_bytes: bytes,
    filename: str,
    application_ids: List[int],
    document_type_id: int = 1,
    category_ids: Optional[List[int]] = None,
    uploaded_by: str = "system"
) -> Tuple[bool, str, Dict[str, Any]]:
    """Process file, generate embeddings, store blob, and index chunks with rollback safety."""
    if category_ids is None:
        category_ids = []

    try:
        filename = safe_filename(filename)
    except ValueError as e:
        return False, str(e), {}

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return False, (
            f"Unsupported file type '{ext or 'none'}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        ), {}

    # Refuse duplicates up front, before touching storage: the original file's blob
    # and chunks must never be overwritten or deleted by a failed re-upload.
    async with db_manager.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM uploaded_files WHERE filename = $1", filename)
    if exists:
        return False, (
            f"A document named '{filename}' already exists. "
            "Delete it first or rename the new file."
        ), {}

    # 1. Stage under a unique temporary name (concurrent uploads never collide)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = STAGING_DIR / f"{uuid.uuid4().hex}{ext}"
    temp_path.write_bytes(file_bytes)

    inserted_file_id = None
    storage_key = None

    try:
        # 2. Parse file into chunks
        if ext in (".csv", ".tsv"):
            chunks = parse_csv_to_chunks(temp_path, filename)
        elif ext == ".xlsx":
            chunks = parse_xlsx_to_chunks(temp_path, filename)
        else:
            md_text = doc_parser.parse_to_markdown(temp_path, filename)
            chunks = doc_parser.chunk_markdown(md_text, filename)

        if not chunks:
            return False, "File parsing produced no indexable text chunks.", {}

        # 3. Resolve Application Names for filtering
        async with db_manager.acquire() as conn:
            app_rows = await conn.fetch("SELECT name FROM applications WHERE id = ANY($1)", application_ids)
            app_names = [r["name"] for r in app_rows] if app_rows else ["General Knowledge"]

        # 4. Generate embeddings in batches (fails loudly if no embedding provider works)
        vectors = await get_embeddings([c["chunk_text"] for c in chunks])

        # 5. Upload original file under a unique key so it can never clobber another blob
        storage_key = f"{uuid.uuid4().hex[:8]}_{filename}"
        storage_url = await storage_client.upload(storage_key, file_bytes)

        # 6. Insert metadata and vector chunks in a single PostgreSQL transaction
        async with db_manager.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    INSERT INTO uploaded_files
                        (filename, file_size, mime_type, storage_url, application_ids, category_ids, document_type_id, indexed_chunks, is_enabled, uploaded_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE, $9)
                    RETURNING id;
                """, filename, len(file_bytes), ext, storage_url, application_ids, category_ids, document_type_id, len(chunks), uploaded_by)
                inserted_file_id = row["id"]

                await conn.executemany("""
                    INSERT INTO primary_vector_chunks
                        (file_id, filename, chunk_index, chunk_text, section_title, dense_vector, application_names, category_ids, document_type_id, is_enabled)
                    VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, $9, TRUE);
                """, [
                    (inserted_file_id, filename, c["chunk_index"], c["chunk_text"], c.get("section_title"),
                     vector_literal(vec), app_names, category_ids, document_type_id)
                    for c, vec in zip(chunks, vectors)
                ])

        logger.info(f"Successfully processed and indexed '{filename}': {len(chunks)} chunks.")
        return True, "File indexed successfully.", {
            "file_id": inserted_file_id,
            "filename": filename,
            "indexed_chunks": len(chunks),
            "storage_url": storage_url
        }

    except Exception as e:
        logger.error(f"Error indexing file {filename}: {e}. Initiating compensation rollback...")
        # The DB transaction rolls itself back; only our own unique blob needs removing.
        if storage_key:
            try:
                await storage_client.delete(storage_key)
            except Exception as cleanup_err:
                logger.error(f"Blob cleanup failure: {cleanup_err}")
        return False, f"Failed to process file: {str(e)}", {}

    finally:
        if temp_path.exists():
            temp_path.unlink()
