"""Knowledge Document Ingestion and File Management API Routes."""
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from pydantic import BaseModel

from src.core.security.auth import get_current_user, require_admin, UserClaims
from src.core.rag.file_service import process_and_index_file
from src.core.db.session import db_manager
from src.core.db.blob import storage_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Knowledge & Files"])

class ListFilesRequest(BaseModel):
    application_id: Optional[int] = None
    page: int = 1
    page_size: int = 50
    search_query: Optional[str] = None

class ToggleStatusRequest(BaseModel):
    file_id: int
    is_enabled: bool

class DeleteFilesRequest(BaseModel):
    file_ids: List[int]

@router.post("/upload_file")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    application_ids: str = Form(...), # JSON array string, e.g. "[1, 2]"
    document_type_id: int = Form(1),
    category_ids: Optional[str] = Form(None),
    user: UserClaims = Depends(require_admin)
):
    """Upload and index a knowledge document with transactional rollback safety."""
    try:
        app_ids = json.loads(application_ids) if isinstance(application_ids, str) else [application_ids]
    except Exception:
        raise HTTPException(status_code=400, detail="application_ids must be a valid JSON array of integers")

    cat_ids = []
    if category_ids:
        try:
            cat_ids = json.loads(category_ids)
        except Exception:
            pass

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Cannot upload empty file")

    success, message, data = await process_and_index_file(
        file_bytes=content,
        filename=file.filename,
        application_ids=app_ids,
        document_type_id=document_type_id,
        category_ids=cat_ids,
        uploaded_by=user.user_id
    )

    if not success:
        return {"success": False, "message": message, "data": {}}

    return {"success": True, "message": message, "data": data}

@router.post("/list_files")
async def list_files_endpoint(
    request: ListFilesRequest,
    user: UserClaims = Depends(get_current_user)
):
    """List uploaded files with active pagination and filtering."""
    offset = (request.page - 1) * request.page_size
    query_parts = ["1=1"]
    params = []

    if request.application_id:
        params.append(request.application_id)
        query_parts.append(f"${len(params)} = ANY(application_ids)")

    if request.search_query:
        params.append(f"%{request.search_query}%")
        query_parts.append(f"filename ILIKE ${len(params)}")

    where_clause = " AND ".join(query_parts)

    async with db_manager.acquire() as conn:
        total = await conn.fetchval(f"SELECT count(*) FROM uploaded_files WHERE {where_clause}", *params)

        params.extend([request.page_size, offset])
        sql = f"""
            SELECT id, filename, file_size, mime_type, storage_url, application_ids, is_enabled, indexed_chunks, created_at
            FROM uploaded_files
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${len(params)-1} OFFSET ${len(params)};
        """
        rows = await conn.fetch(sql, *params)

        files = [
            {
                "id": r["id"],
                "filename": r["filename"],
                "file_size": r["file_size"],
                "mime_type": r["mime_type"],
                "storage_url": r["storage_url"],
                "application_ids": r["application_ids"],
                "is_enabled": r["is_enabled"],
                "indexed_chunks": r["indexed_chunks"],
                "created_at": r["created_at"].isoformat()
            }
            for r in rows
        ]

    return {
        "total": total,
        "page": request.page,
        "page_size": request.page_size,
        "files": files
    }

@router.post("/toggle_file_status")
async def toggle_file_status_endpoint(
    request: ToggleStatusRequest,
    user: UserClaims = Depends(require_admin)
):
    """Toggle document availability in vector retrieval without deleting the file."""
    async with db_manager.acquire() as conn:
        async with conn.transaction():
            # Update uploaded_files
            row = await conn.fetchrow("""
                UPDATE uploaded_files
                SET is_enabled = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING filename, indexed_chunks;
            """, request.is_enabled, request.file_id)

            if not row:
                raise HTTPException(status_code=404, detail="File ID not found")

            # Update associated vector chunks
            await conn.execute("""
                UPDATE primary_vector_chunks
                SET is_enabled = $1
                WHERE file_id = $2;
            """, request.is_enabled, request.file_id)

    status_str = "enabled" if request.is_enabled else "disabled"
    return {
        "success": True,
        "file_id": request.file_id,
        "is_enabled": request.is_enabled,
        "message": f"File '{row['filename']}' ({row['indexed_chunks']} chunks) is now {status_str}."
    }

@router.post("/delete_files")
async def delete_files_endpoint(
    request: DeleteFilesRequest,
    user: UserClaims = Depends(require_admin)
):
    """Delete files from database, vector collection, and storage."""
    deleted_count = 0
    async with db_manager.acquire() as conn:
        for file_id in request.file_ids:
            row = await conn.fetchrow("SELECT filename FROM uploaded_files WHERE id = $1", file_id)
            if row:
                filename = row["filename"]
                await storage_client.delete(filename)
                await conn.execute("DELETE FROM uploaded_files WHERE id = $1", file_id)
                deleted_count += 1

    return {"success": True, "deleted_count": deleted_count}

@router.get("/files/{file_id}/chunks")
async def get_file_chunks_endpoint(
    file_id: int,
    user: UserClaims = Depends(get_current_user)
):
    """Retrieve all indexed vector chunks for a specific document."""
    async with db_manager.acquire() as conn:
        doc = await conn.fetchrow("SELECT filename, indexed_chunks FROM uploaded_files WHERE id = $1", file_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        rows = await conn.fetch("""
            SELECT id, chunk_index, section_title, chunk_text, length(chunk_text) as char_count
            FROM primary_vector_chunks
            WHERE file_id = $1
            ORDER BY chunk_index ASC;
        """, file_id)

        return {
            "file_id": file_id,
            "filename": doc["filename"],
            "total_chunks": len(rows),
            "chunks": [
                {
                    "id": str(r["id"]),
                    "chunk_index": r["chunk_index"],
                    "section_title": r["section_title"] or "General",
                    "chunk_text": r["chunk_text"],
                    "char_count": r["char_count"]
                }
                for r in rows
            ]
        }
