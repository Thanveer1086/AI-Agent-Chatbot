"""Human-in-the-loop approvals for tools that can change external systems.

Flow:
1. The agent plans a write tool -> `create_pending_approval` stores the exact call.
2. The chat shows an approval card; nothing has run yet.
3. The user approves -> `approve` atomically claims the row (pending -> executing),
   runs exactly the stored arguments once, and records the result.
   Rejecting or letting it expire means the tool never runs.
"""
import json
import uuid
import logging
from typing import Any, Dict, Optional

from src.config import settings
from src.core.db.session import db_manager
from src.core.mcp.manager import mcp_manager
from src.core.security.guardrails import sanitize_output_text

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 4000


class ApprovalError(Exception):
    """Raised when an approval cannot be decided (missing, not yours, already decided, expired)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _row_to_dict(row) -> Dict[str, Any]:
    args = row["arguments"]
    if isinstance(args, str):
        args = json.loads(args)
    return {
        "approval_id": str(row["id"]),
        "session_id": str(row["session_id"]) if row["session_id"] else None,
        "tool_name": row["tool_name"],
        "arguments": args,
        "reason": row["reason"],
        "status": row["status"],
        "result": row["result"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None,
        **mcp_manager.describe_tool(row["tool_name"]),
    }


async def create_pending_approval(
    session_id: str, user_id: str, tool_name: str, arguments: Dict[str, Any], reason: Optional[str]
) -> str:
    approval_id = str(uuid.uuid4())
    async with db_manager.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tool_approvals (id, session_id, user_id, tool_name, arguments, reason)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6);
            """,
            approval_id, session_id, user_id, tool_name, json.dumps(arguments, default=str), reason,
        )
    logger.info(f"Tool '{tool_name}' is waiting for approval ({approval_id}).")
    return approval_id


async def _expire_stale(conn) -> None:
    await conn.execute(
        """
        UPDATE tool_approvals SET status = 'expired', decided_at = NOW()
        WHERE status = 'pending' AND created_at < NOW() - make_interval(mins => $1);
        """,
        settings.APPROVAL_TTL_MINUTES,
    )


async def get_approvals(user_id: str, ids: Optional[list] = None, status: Optional[str] = None) -> list:
    async with db_manager.acquire() as conn:
        await _expire_stale(conn)
        rows = await conn.fetch(
            """
            SELECT * FROM tool_approvals
            WHERE user_id = $1
              AND ($2::uuid[] IS NULL OR id = ANY($2::uuid[]))
              AND ($3::text IS NULL OR status = $3)
            ORDER BY created_at DESC
            LIMIT 100;
            """,
            user_id, ids, status,
        )
    return [_row_to_dict(r) for r in rows]


async def _claim(approval_id: str, user_id: str, new_status: str) -> Dict[str, Any]:
    """Atomically move a pending approval owned by `user_id` to `new_status`."""
    async with db_manager.acquire() as conn:
        await _expire_stale(conn)
        row = await conn.fetchrow(
            """
            UPDATE tool_approvals SET status = $3, decided_at = NOW()
            WHERE id = $1::uuid AND user_id = $2 AND status = 'pending'
            RETURNING *;
            """,
            approval_id, user_id, new_status,
        )
        if row is None:
            existing = await conn.fetchrow(
                "SELECT status FROM tool_approvals WHERE id = $1::uuid AND user_id = $2;",
                approval_id, user_id,
            )
    if row is None:
        if existing is None:
            raise ApprovalError(404, "Approval request not found")
        raise ApprovalError(409, f"This request is already {existing['status']}")
    return _row_to_dict(row)


async def _record_outcome_message(session_id: Optional[str], content: str, tool_record: Optional[dict]) -> Optional[Dict[str, Any]]:
    """Add the outcome to the conversation so later turns know what happened."""
    if not session_id:
        return None
    message_id = str(uuid.uuid4())
    async with db_manager.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, tool_calls)
            VALUES ($1::uuid, $2::uuid, 'assistant', $3, $4::jsonb);
            """,
            message_id, session_id, content, json.dumps([tool_record] if tool_record else [], default=str),
        )
        await conn.execute("UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1::uuid;", session_id)
    return {"id": message_id, "role": "assistant", "content": content}


async def approve(approval_id: str, user_id: str) -> Dict[str, Any]:
    """Run the stored tool call exactly once and record the outcome."""
    from src.core.mcp.executor import execute_single_tool

    approval = await _claim(approval_id, user_id, "executing")
    record, _ = await execute_single_tool(
        f"call_approved_{approval_id[:8]}", approval["tool_name"], dict(approval["arguments"])
    )
    output = sanitize_output_text(str(record["output"]))[:MAX_RESULT_CHARS]
    final_status = "executed" if record["status"] == "success" else "failed"

    async with db_manager.acquire() as conn:
        await conn.execute(
            "UPDATE tool_approvals SET status = $2, result = $3 WHERE id = $1::uuid;",
            approval_id, final_status, output,
        )

    title = approval["title"]
    if final_status == "executed":
        content = f"✅ Approved action **{title}** was executed.\n\n**Result:**\n```\n{output[:1500]}\n```"
    else:
        content = f"⚠️ Approved action **{title}** failed.\n\n```\n{output[:1500]}\n```"
    message = await _record_outcome_message(approval["session_id"], content, {**record, "output": output})

    approval.update({"status": final_status, "result": output})
    return {"approval": approval, "message": message}


async def reject(approval_id: str, user_id: str) -> Dict[str, Any]:
    approval = await _claim(approval_id, user_id, "rejected")
    content = f"❌ Action **{approval['title']}** was rejected. Nothing was changed."
    message = await _record_outcome_message(approval["session_id"], content, None)
    return {"approval": approval, "message": message}
