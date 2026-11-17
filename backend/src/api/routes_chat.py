"""Chat and Server-Sent Events (SSE) streaming route handlers."""
import json
import uuid
import logging
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from src.config import settings
from src.core.security.auth import get_current_user, UserClaims
from src.core.security.guardrails import (
    StreamingRedactor,
    check_rate_limit,
    sanitize_output_text,
    validate_input_query,
)
from src.core.agent.graph import agent_app
from src.core.db.session import db_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat & Streaming"])


class ChatRequest(BaseModel):
    session_id: Optional[uuid.UUID] = None
    application_id: int = 1
    message: str = Field(..., min_length=1, max_length=5000)


class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def get_session_owner(conn, session_id: str) -> Optional[str]:
    return await conn.fetchval("SELECT user_id FROM chat_sessions WHERE id = $1::uuid", session_id)


async def require_session_owner(conn, session_id: str, user: UserClaims) -> None:
    """404 unless the session exists and belongs to the caller (no existence leak)."""
    owner = await get_session_owner(conn, session_id)
    if owner is None or owner != user.user_id:
        raise HTTPException(status_code=404, detail="Session not found")


async def stream_agent_execution(
    request: ChatRequest,
    user: UserClaims
) -> AsyncGenerator[str, None]:
    """Generator yielding formatted Server-Sent Events for agent execution."""
    session_id = str(request.session_id or uuid.uuid4())
    message_id = str(uuid.uuid4())
    done = sse("done", {"message_id": message_id, "session_id": session_id})

    # 0. Rate Limiting Protection (Max 35 queries/minute)
    if not check_rate_limit(user.user_id):
        yield sse("error", {"code": "RATE_LIMIT_EXCEEDED", "message": "Request limit reached. Please wait a moment before sending another query."})
        yield done
        return

    # 1. Input Guardrail Verification
    is_safe, cleaned_or_error = validate_input_query(request.message)
    if not is_safe:
        yield sse("error", {"code": "GUARDRAIL_BLOCKED", "message": cleaned_or_error})
        yield done
        return

    # 2. Ownership check, multi-turn history and user message persistence
    conversation_history = []
    try:
        async with db_manager.acquire() as conn:
            owner = await get_session_owner(conn, session_id)
            if owner is not None and owner != user.user_id:
                yield sse("error", {"code": "SESSION_FORBIDDEN", "message": "This conversation does not belong to you."})
                yield done
                return

            if owner is not None and settings.CHAT_HISTORY_MESSAGES > 0:
                # Most recent N messages, returned oldest-first
                prior_rows = await conn.fetch("""
                    SELECT role, content FROM (
                        SELECT role, content, created_at
                        FROM chat_messages
                        WHERE session_id = $1::uuid
                        ORDER BY created_at DESC
                        LIMIT $2
                    ) recent
                    ORDER BY created_at ASC;
                """, session_id, settings.CHAT_HISTORY_MESSAGES)
                for r in prior_rows:
                    if r["role"] == "user":
                        conversation_history.append(HumanMessage(content=r["content"]))
                    elif r["role"] == "assistant":
                        conversation_history.append(AIMessage(content=r["content"]))

            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO chat_sessions (id, user_id, application_id, title, updated_at)
                    VALUES ($1::uuid, $2, $3, $4, NOW())
                    ON CONFLICT (id) DO UPDATE SET updated_at = NOW()
                    WHERE chat_sessions.user_id = EXCLUDED.user_id;
                """, session_id, user.user_id, request.application_id, request.message[:40])
                await conn.execute("""
                    INSERT INTO chat_messages (id, session_id, role, content)
                    VALUES ($1::uuid, $2::uuid, 'user', $3);
                """, str(uuid.uuid4()), session_id, request.message)
    except Exception as e:
        logger.warning(f"Could not load conversation history/persist message: {e}")

    conversation_history.append(HumanMessage(content=cleaned_or_error))

    # 3. Stream Graph Execution
    initial_state = {
        "session_id": session_id,
        "application_id": request.application_id,
        "application_name": "General Knowledge",
        "messages": conversation_history,
        "iteration_count": 0,
        "tool_calls_queue": [],
        "tool_execution_history": [],
        "citations": [],
        "intermediate_thoughts": [],
        "final_answer": None,
        "status": "planning"
    }

    citations_collected = []
    thoughts_collected = []
    tools_collected = []
    tool_starts_emitted = set()
    tools_emitted = set()
    citations_emitted = set()
    redactor = StreamingRedactor()
    streamed_any_token = False
    answer_text = ""

    try:
        async for mode, chunk in agent_app.astream(initial_state, stream_mode=["updates", "custom"]):
            # Live answer tokens written by the answer node
            if mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    safe = redactor.feed(chunk.get("text", ""))
                    if safe:
                        streamed_any_token = True
                        yield sse("token", {"text": safe})
                continue

            for node_name, node_output in (chunk or {}).items():
                if not isinstance(node_output, dict):
                    continue

                for thought in node_output.get("intermediate_thoughts", []):
                    thoughts_collected.append(thought)
                    yield sse("thought_step", thought)

                for tool in node_output.get("tool_calls_queue", []):
                    if tool["call_id"] not in tool_starts_emitted:
                        tool_starts_emitted.add(tool["call_id"])
                        yield sse("tool_start", {"tool_name": tool["name"], "call_id": tool["call_id"], "arguments": tool["arguments"]})

                for record in node_output.get("tool_execution_history", []):
                    if record["call_id"] not in tools_emitted:
                        tools_emitted.add(record["call_id"])
                        tools_collected.append(record)
                        yield sse("tool_result", {**record, "output": sanitize_output_text(str(record["output"]))})

                for cit in node_output.get("citations", []):
                    key = cit.get("chunk_id") or json.dumps(cit, sort_keys=True, default=str)
                    if key not in citations_emitted:
                        citations_emitted.add(key)
                        citations_collected.append(cit)
                        yield sse("citation", cit)

                if node_output.get("final_answer"):
                    answer_text = sanitize_output_text(node_output["final_answer"])

        # Release any text still held back by the redactor
        tail = redactor.flush()
        if tail:
            streamed_any_token = True
            yield sse("token", {"text": tail})
        if answer_text and not streamed_any_token:
            yield sse("token", {"text": answer_text})

        if answer_text:
            try:
                async with db_manager.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO chat_messages (id, session_id, role, content, thought_traces, tool_calls, citations)
                        VALUES ($1::uuid, $2::uuid, 'assistant', $3, $4::jsonb, $5::jsonb, $6::jsonb);
                    """, message_id, session_id, answer_text,
                        json.dumps(thoughts_collected, default=str),
                        json.dumps(tools_collected, default=str),
                        json.dumps(citations_collected, default=str))
                    await conn.execute("UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1::uuid;", session_id)
            except Exception as e:
                logger.warning(f"Failed to persist chat message: {e}")

        yield done

    except Exception as e:
        logger.exception(f"Error during agent execution stream: {e}")
        yield sse("error", {"code": "AGENT_ERROR", "message": "The agent hit an internal error. Please try again."})
        yield done


@router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    user: UserClaims = Depends(get_current_user)
):
    """Real-time SSE streaming agent chat endpoint."""
    return StreamingResponse(
        stream_agent_execution(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/sessions")
async def list_chat_sessions(
    application_id: Optional[int] = 1,
    user: UserClaims = Depends(get_current_user)
):
    """List recent conversation sessions for the active user."""
    async with db_manager.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE user_id = $1 AND ($2::int IS NULL OR application_id = $2)
            ORDER BY updated_at DESC
            LIMIT 50;
        """, user.user_id, application_id)
        return [
            {
                "id": str(r["id"]),
                "title": r["title"] or "New Conversation",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None
            }
            for r in rows
        ]


def _parse_json(val):
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return []
    return val


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: uuid.UUID,
    user: UserClaims = Depends(get_current_user)
):
    """Retrieve full message history for a conversation session owned by the caller."""
    async with db_manager.acquire() as conn:
        await require_session_owner(conn, str(session_id), user)
        rows = await conn.fetch("""
            SELECT id, role, content, thought_traces, tool_calls, citations, created_at
            FROM chat_messages
            WHERE session_id = $1::uuid
            ORDER BY created_at ASC;
        """, str(session_id))

    result = []
    for r in rows:
        result.append({
            "id": str(r["id"]),
            "role": r["role"],
            "content": r["content"],
            "thoughts": _parse_json(r["thought_traces"]),
            "tool_traces": [
                {
                    "tool_name": t.get("tool_name", "tool"),
                    "call_id": t.get("call_id", ""),
                    "status": t.get("status", "success"),
                    "duration_ms": t.get("latency_ms"),
                    "summary": str(t.get("output", ""))[:100] + ("..." if len(str(t.get("output", ""))) > 100 else "")
                }
                for t in _parse_json(r["tool_calls"])
            ],
            "citations": _parse_json(r["citations"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None
        })
    return result


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: uuid.UUID,
    user: UserClaims = Depends(get_current_user)
):
    """Delete a conversation session and all its messages."""
    async with db_manager.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM chat_sessions WHERE id = $1::uuid AND user_id = $2 RETURNING id;",
            str(session_id), user.user_id,
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "deleted_session_id": str(session_id)}


@router.patch("/sessions/{session_id}")
async def rename_chat_session(
    session_id: uuid.UUID,
    request: RenameSessionRequest,
    user: UserClaims = Depends(get_current_user)
):
    """Rename a conversation session title."""
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be blank")
    async with db_manager.acquire() as conn:
        updated = await conn.fetchval("""
            UPDATE chat_sessions
            SET title = $1, updated_at = NOW()
            WHERE id = $2::uuid AND user_id = $3
            RETURNING id;
        """, title, str(session_id), user.user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "session_id": str(session_id), "new_title": title}
