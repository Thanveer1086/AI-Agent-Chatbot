"""Admin Review, Q&A Overrides, Master Data, and User Feedback Routes."""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.security.auth import get_current_user, require_admin, UserClaims
from src.core.db.session import db_manager
from src.core.rag.embeddings import get_embedding, vector_literal
from src.core.rag import index_admin
from src.core.rag.index_admin import incompatibility_reason, is_index_compatible

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Admin Review & Feedback"])

class FeedbackRequest(BaseModel):
    message_id: str
    rating: str = Field(..., pattern="^(satisfactory|unsatisfactory|noresponse)$")
    comment: Optional[str] = None

class OverrideAnswerRequest(BaseModel):
    question_text: str = Field(..., min_length=3)
    approved_answer: str = Field(..., min_length=5)
    application_id: int = 1

@router.post("/submit/feedback")
async def submit_feedback_endpoint(
    request: FeedbackRequest,
    user: UserClaims = Depends(get_current_user)
):
    """Record user satisfaction rating on an agent answer."""
    try:
        message_uuid = str(uuid.UUID(request.message_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="message_id must be a valid message UUID")

    async with db_manager.acquire() as conn:
        # Only assistant messages in the caller's own sessions can be rated.
        owned = await conn.fetchval("""
            SELECT 1 FROM chat_messages m
            JOIN chat_sessions s ON s.id = m.session_id
            WHERE m.id = $1::uuid AND m.role = 'assistant' AND s.user_id = $2;
        """, message_uuid, user.user_id)
        if not owned:
            raise HTTPException(status_code=404, detail="Message not found")

        await conn.execute("""
            INSERT INTO feedback_records (message_id, rating, comment)
            VALUES ($1::uuid, $2, $3);
        """, message_uuid, request.rating, request.comment)
    return {"success": True, "message": "Feedback recorded successfully."}

@router.post("/override_answer")
async def override_answer_endpoint(
    request: OverrideAnswerRequest,
    user: UserClaims = Depends(require_admin)
):
    """Publish an authoritative approved answer into the QA expansion vector collection."""
    # Generate embedding for the approved Q&A
    if not is_index_compatible():
        raise HTTPException(status_code=409, detail=f"Embedding index mismatch: {incompatibility_reason()} Re-index first.")
    try:
        dense_vec = await get_embedding(request.question_text, is_query=True)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding service unavailable: {e}")
    vec_str = vector_literal(dense_vec)

    async with db_manager.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO approved_answers 
                (question_text, approved_answer, dense_vector, application_id, status, author)
            VALUES ($1, $2, $3::vector, $4, 'answer_embedded', $5)
            RETURNING id;
        """, request.question_text, request.approved_answer, vec_str, request.application_id, user.user_id)

    logger.info(f"Published approved override answer #{row['id']} for '{request.question_text}'.")
    return {
        "success": True,
        "override_id": row["id"],
        "message": "Approved answer successfully vectorized and published to QA expansion database."
    }

@router.get("/master_data")
async def get_master_data_endpoint(
    user: UserClaims = Depends(get_current_user)
):
    """Fetch active application domains and document types."""
    async with db_manager.acquire() as conn:
        apps = await conn.fetch("SELECT id, name, description FROM applications ORDER BY id ASC;")
        doc_types = await conn.fetch("SELECT id, name FROM document_types ORDER BY id ASC;")

    return {
        "applications": [{"id": r["id"], "name": r["name"], "description": r["description"]} for r in apps],
        "document_types": [{"id": r["id"], "name": r["name"]} for r in doc_types]
    }


@router.get("/embeddings/status")
async def embedding_status_endpoint(user: UserClaims = Depends(get_current_user)):
    """Which embedding provider is configured, which one built the stored vectors, and whether they match."""
    return await index_admin.check_index()


@router.post("/embeddings/reindex")
async def reindex_embeddings_endpoint(user: UserClaims = Depends(require_admin)):
    """Re-embed every chunk and approved answer with the configured provider (admin only)."""
    try:
        return {"success": True, **(await index_admin.reindex_all())}
    except Exception as e:
        logger.error(f"Re-index failed: {e}")
        raise HTTPException(status_code=500, detail=f"Re-index failed, nothing was changed: {e}")
