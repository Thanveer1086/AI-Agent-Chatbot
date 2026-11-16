"""Chat and Server-Sent Events (SSE) streaming route handlers."""
import json
import uuid
import asyncio
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional

from src.core.security.auth import get_current_user, UserClaims
from src.core.security.guardrails import validate_input_query, sanitize_output_text, check_rate_limit
from src.core.agent.graph import agent_app
from src.core.db.session import db_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat & Streaming"])

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    application_id: int = 1
    message: str = Field(..., min_length=1, max_length=5000)

class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)

async def stream_agent_execution(
    request: ChatRequest,
    user: UserClaims
) -> AsyncGenerator[str, None]:
    """Generator yielding formatted Server-Sent Events for agent execution."""
    session_id = request.session_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # 0. Rate Limiting Protection (Max 35 queries/minute)
    if not check_rate_limit(user.user_id):
        yield f"event: error\ndata: {json.dumps({'code': 'RATE_LIMIT_EXCEEDED', 'message': 'Request limit reached. Please wait a moment before sending another query.'})}\n\n"
        yield f"event: done\ndata: {json.dumps({'message_id': message_id, 'session_id': session_id})}\n\n"
        return

    # 1. Input Guardrail Verification
    is_safe, cleaned_or_error = validate_input_query(request.message)
    if not is_safe:
        yield f"event: error\ndata: {json.dumps({'code': 'GUARDRAIL_BLOCKED', 'message': cleaned_or_error})}\n\n"
        yield f"event: done\ndata: {json.dumps({'message_id': message_id, 'session_id': session_id})}\n\n"
        return

    # 2. Multi-Turn History Retrieval & Record User Message
    conversation_history = []
    user_msg_id = str(uuid.uuid4())
    try:
        async with db_manager.acquire() as conn:
            # Fetch up to 8 prior messages in this session for conversational context
            prior_rows = await conn.fetch("""
                SELECT role, content
                FROM chat_messages
                WHERE session_id = $1::uuid
                ORDER BY created_at ASC
                LIMIT 8;
            """, session_id)
            for r in prior_rows:
                if r["role"] == "user":
                    conversation_history.append(HumanMessage(content=r["content"]))
                elif r["role"] == "assistant":
                    conversation_history.append(AIMessage(content=r["content"]))

            await conn.execute("""
                INSERT INTO chat_sessions (id, user_id, application_id, title, updated_at)
                VALUES ($1::uuid, $2, $3, $4, NOW())
                ON CONFLICT (id) DO UPDATE SET updated_at = NOW();
            """, session_id, user.user_id, request.application_id, request.message[:40])

            await conn.execute("""
                INSERT INTO chat_messages (id, session_id, role, content)
                VALUES ($1::uuid, $2::uuid, 'user', $3);
            """, user_msg_id, session_id, request.message)
    except Exception as e:
        logger.warning(f"Could not load conversation history/persist message: {e}")

    # Append current user message
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
    thoughts_emitted = set()
    tools_emitted = set()

    try:
        async for chunk in agent_app.astream(initial_state):
            for node_name, node_output in chunk.items():
                # Emit Thoughts
                for thought in node_output.get("intermediate_thoughts", []):
                    step_key = f"{thought['step']}_{thought['thought'][:20]}"
                    if step_key not in thoughts_emitted:
                        thoughts_emitted.add(step_key)
                        thoughts_collected.append(thought)
                        yield f"event: thought_step\ndata: {json.dumps(thought)}\n\n"
                        await asyncio.sleep(0.05)

                # Emit Tool Start / Execution Traces
                for tool in node_output.get("tool_calls_queue", []):
                    yield f"event: tool_start\ndata: {json.dumps({'tool_name': tool['name'], 'call_id': tool['call_id'], 'arguments': tool['arguments']})}\n\n"

                for record in node_output.get("tool_execution_history", []):
                    if record["call_id"] not in tools_emitted:
                        tools_emitted.add(record["call_id"])
                        tools_collected.append(record)
                        yield f"event: tool_result\ndata: {json.dumps(record)}\n\n"

                # Collect Citations
                for cit in node_output.get("citations", []):
                    citations_collected.append(cit)
                    yield f"event: citation\ndata: {json.dumps(cit)}\n\n"

                # Stream Final Answer Tokens
                if "final_answer" in node_output and node_output["final_answer"]:
                    answer_text = sanitize_output_text(node_output["final_answer"])
                    # Simulate token stream chunks
                    words = answer_text.split(" ")
                    for i, word in enumerate(words):
                        trailing = " " if i < len(words) - 1 else ""
                        yield f"event: token\ndata: {json.dumps({'text': word + trailing})}\n\n"
                        await asyncio.sleep(0.015)

                    # Persist message in PostgreSQL
                    try:
                        async with db_manager.acquire() as conn:
                            await conn.execute("""
                                INSERT INTO chat_messages (id, session_id, role, content, thought_traces, tool_calls, citations)
                                VALUES ($1::uuid, $2::uuid, 'assistant', $3, $4::jsonb, $5::jsonb, $6::jsonb);
                            """, message_id, session_id, answer_text, json.dumps(thoughts_collected), json.dumps(tools_collected), json.dumps(citations_collected))
                            await conn.execute("UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1::uuid;", session_id)
                    except Exception as e:
                        logger.warning(f"Failed to persist chat message: {e}")

        # Final Done Event
        yield f"event: done\ndata: {json.dumps({'message_id': message_id, 'session_id': session_id})}\n\n"

    except Exception as e:
        logger.error(f"Error during agent execution stream: {e}")
        yield f"event: error\ndata: {json.dumps({'code': 'AGENT_ERROR', 'message': str(e)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'message_id': message_id, 'session_id': session_id})}\n\n"

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

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user: UserClaims = Depends(get_current_user)
):
    """Retrieve full message history for a specific conversation session."""
    async with db_manager.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, role, content, thought_traces, tool_calls, citations, created_at
            FROM chat_messages
            WHERE session_id = $1::uuid
            ORDER BY created_at ASC;
        """, session_id)
        
        result = []
        for r in rows:
            # Parse jsonb fields if stored as string or None
            def parse_json(val):
                if val is None: return []
                if isinstance(val, str):
                    try: return json.loads(val)
                    except: return []
                return val

            result.append({
                "id": str(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "thoughts": parse_json(r["thought_traces"]),
                "tool_traces": [
                    {
                        "tool_name": t.get("tool_name", "tool"),
                        "call_id": t.get("call_id", ""),
                        "status": t.get("status", "success"),
                        "duration_ms": t.get("latency_ms"),
                        "summary": str(t.get("output", ""))[:100] + ("..." if len(str(t.get("output", ""))) > 100 else "")
                    }
                    for t in parse_json(r["tool_calls"])
                ],
                "citations": parse_json(r["citations"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None
            })
        return result

@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    user: UserClaims = Depends(get_current_user)
):
    """Delete a conversation session and all its messages."""
    async with db_manager.acquire() as conn:
        await conn.execute("DELETE FROM chat_sessions WHERE id = $1::uuid AND user_id = $2;", session_id, user.user_id)
        return {"status": "success", "deleted_session_id": session_id}

@router.patch("/sessions/{session_id}")
async def rename_chat_session(
    session_id: str,
    request: RenameSessionRequest,
    user: UserClaims = Depends(get_current_user)
):
    """Rename a conversation session title."""
    async with db_manager.acquire() as conn:
        await conn.execute("""
            UPDATE chat_sessions
            SET title = $1, updated_at = NOW()
            WHERE id = $2::uuid AND user_id = $3;
        """, request.title.strip(), session_id, user.user_id)
        return {"status": "success", "session_id": session_id, "new_title": request.title.strip()}
