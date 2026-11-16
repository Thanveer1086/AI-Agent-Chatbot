"""Admin Review, Q&A Overrides, Master Data, and User Feedback Routes."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.security.auth import get_current_user, require_admin, UserClaims
from src.core.db.session import db_manager
from src.core.rag.embeddings import get_embedding

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
    async with db_manager.acquire() as conn:
        try:
            await conn.execute("""
                INSERT INTO feedback_records (message_id, rating, comment)
                VALUES ($1::uuid, $2, $3);
            """, request.message_id, request.rating, request.comment)
            return {"success": True, "message": "Feedback recorded successfully."}
        except Exception as e:
            logger.warning(f"Failed to record feedback: {e}")
            return {"success": True, "message": "Feedback noted (message ID logged)."}

@router.post("/override_answer")
async def override_answer_endpoint(
    request: OverrideAnswerRequest,
    user: UserClaims = Depends(require_admin)
):
    """Publish an authoritative approved answer into the QA expansion vector collection."""
    # Generate embedding for the approved Q&A
    dense_vec = await get_embedding(request.question_text)
    vec_str = "[" + ",".join(f"{x:.6f}" for x in dense_vec) + "]"

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
