"""Human-in-the-loop approval endpoints for tools that change external systems."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.agent import approvals
from src.core.security.auth import UserClaims, get_current_user

router = APIRouter(prefix="/api/tools/approvals", tags=["Tool Approvals"])

VALID_STATUSES = {"pending", "executing", "executed", "failed", "rejected", "expired"}


@router.get("")
async def list_approvals(
    status: Optional[str] = Query(None, description="Filter by status, e.g. 'pending'"),
    user: UserClaims = Depends(get_current_user),
):
    """List the caller's approval requests (newest first)."""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    return {"approvals": await approvals.get_approvals(user.user_id, status=status)}


@router.post("/{approval_id}/approve")
async def approve_tool_call(approval_id: uuid.UUID, user: UserClaims = Depends(get_current_user)):
    """Run the stored tool call exactly once. Only the user who owns the request can approve it."""
    try:
        return await approvals.approve(str(approval_id), user.user_id)
    except approvals.ApprovalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{approval_id}/reject")
async def reject_tool_call(approval_id: uuid.UUID, user: UserClaims = Depends(get_current_user)):
    """Reject the request; the tool never runs."""
    try:
        return await approvals.reject(str(approval_id), user.user_id)
    except approvals.ApprovalError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
