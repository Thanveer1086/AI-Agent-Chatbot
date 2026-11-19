"""LangGraph Nodes: Planner, Tool Executor, Reflection, and Synthesizer."""
import re
import json
import time
import difflib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from langchain_core.messages import BaseMessage, HumanMessage

from src.config import settings
from src.core import llm
from src.core.agent.approvals import create_pending_approval
from src.core.agent.state import AgentState, ThoughtStepRecord
from src.core.db.session import db_manager
from src.core.mcp.executor import execute_tools_parallel
from src.core.mcp.manager import mcp_manager
from src.core.security.guardrails import UNTRUSTED_DATA_RULE, wrap_untrusted

logger = logging.getLogger(__name__)

KNOWLEDGE_TOOL = "knowledge_base_search"
MAX_TOOLS_PER_STEP = 3
MAX_KB_SEARCHES_PER_TURN = 2
MAX_HISTORY_CHARS = 2000
MAX_TOOL_OUTPUT_CHARS = 12000

# Keywords indicating intent for internal company knowledge, meetings, or uploaded documents
INTERNAL_INTENT_PATTERNS = [
    r"\b(meeting|sync|transcript|notes|minutes|agenda|discussion|summary|summarize|action items|takeaway|takeaways|brief|recording)\b",
    r"\b(policy|handbook|reimburse|expense|benefit|vacation|leave|ticket|guideline|contract|procedure|rule|uploaded|attachment|company|internal|doc|docx|pdf|guide|spec|specification|report|project|review|overview|details|explanation)\b",
    r"\b(our\s+[a-z]+|my\s+(team|manager|leave|policy|expense|salary|benefit)|hr\b|it support)\b"
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thought(step: int, text: str) -> ThoughtStepRecord:
    return {"step": step, "thought": text, "timestamp": _now()}


def _role(m: BaseMessage) -> str:
    return "user" if isinstance(m, HumanMessage) else "assistant"


def _history_as_messages(messages: List[BaseMessage]) -> List[Dict[str, str]]:
    """Prior turns (everything except the current question) in provider-neutral form."""
    return [
        {"role": _role(m), "content": str(m.content)[:MAX_HISTORY_CHARS]}
        for m in messages[:-1]
    ]


def _history_as_text(messages: List[BaseMessage], limit: int = 6) -> str:
    prior = messages[:-1][-limit:]
    return "\n".join(f"{_role(m).title()}: {str(m.content)[:600]}" for m in prior)


async def check_internal_search_needed(query: str) -> Tuple[bool, Optional[str]]:
    """Determine if query is targeted at internal company documents, meetings, or uploaded files."""
    query_lower = query.lower().strip()

    for pattern in INTERNAL_INTENT_PATTERNS:
        if re.search(pattern, query_lower):
            return True, None

    try:
        async with db_manager.acquire() as conn:
            rows = await conn.fetch("SELECT filename FROM uploaded_files WHERE is_enabled = TRUE;")
        query_words = [w for w in re.findall(r"[a-zA-Z0-9_-]+", query_lower) if len(w) >= 3]
        for r in rows:
            clean_fname = re.sub(r"\.[a-zA-Z0-9]+$", "", r["filename"]).lower()
            fname_tokens = [w for w in re.findall(r"[a-zA-Z0-9_-]+", clean_fname) if len(w) >= 3]
            for q_word in query_words:
                for f_token in fname_tokens:
                    if q_word in f_token or f_token in q_word:
                        return True, clean_fname
                    if difflib.SequenceMatcher(None, q_word, f_token).ratio() >= 0.72:
                        return True, clean_fname
    except Exception as e:
        logger.warning(f"Error checking active filenames: {e}")

    return False, None


def _describe_params(schema: Dict[str, Any]) -> str:
    props = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    parts = []
    for name, spec in props.items():
        typ = spec.get("type", "any") if isinstance(spec, dict) else "any"
        parts.append(f"{name}{'' if name in required else '?'}: {typ}")
    return ", ".join(parts)


def _tools_catalog() -> str:
    lines = [
        f"- {KNOWLEDGE_TOOL}(query: string): Searches internal company documents, meeting notes, "
        "transcripts, policies, specifications and uploaded files."
    ]
    for full_name, t in mcp_manager.discovered_tools.items():
        orig = t.get("original_tool", {})
        params = _describe_params(orig.get("inputSchema", {}) or {})
        desc = (orig.get("description") or "Execute tool").replace("\n", " ")[:200]
        lines.append(f"- {full_name}({params}): {desc}")
    return "\n".join(lines)


def prepare_arguments(tool: str, arguments: Any, standalone_query: str, application_id: int) -> Dict[str, Any]:
    """Normalise planner arguments and fill the few values the system owns."""
    args = dict(arguments) if isinstance(arguments, dict) else {}
    if tool == KNOWLEDGE_TOOL:
        query = args.get("query")
        args = {
            "query": query if isinstance(query, str) and query.strip() else standalone_query,
            # The application scope comes from the chat request, never from the model.
            "application_id": application_id,
        }
    elif tool.endswith("search_repositories") and not args.get("query") and mcp_manager.authenticated_user:
        args["query"] = f"user:{mcp_manager.authenticated_user}"
    return args


def _call_signature(name: str, args: Dict[str, Any]) -> str:
    return name + json.dumps(args, sort_keys=True, default=str)


PLANNER_SYSTEM = (
    "You are the planning module of an autonomous AI agent. Decide which tools (if any) must run "
    "next to answer the user's latest message. Use the conversation to resolve references such as "
    "'it', 'that one' or 'the second repo'. Only use tool names from the catalog and pass arguments "
    "that match each tool's parameters. Independent tools may run in the same step (max "
    f"{MAX_TOOLS_PER_STEP}). Return an empty tool_calls list when the evidence so far is enough, "
    "or when the question is general knowledge or small talk. Never repeat a call that already ran "
    "with the same arguments. If a knowledge_base_search already returned relevant passages, do NOT "
    "search again with reworded queries: return an empty tool_calls list so the answer can be written. "
    + UNTRUSTED_DATA_RULE
)


PLANNER_JSON_ATTEMPTS = 2


async def _plan_with_retry(prompt: str) -> Dict[str, Any]:
    """Ask the planner for JSON; if the reply is not valid JSON, retry once with a correction.

    Small models (e.g. Flash-Lite) occasionally emit malformed JSON such as an unescaped
    quote. One corrective retry fixes almost all of these without falling back to the
    much weaker keyword heuristic.
    """
    messages = [{"role": "user", "content": prompt}]
    last_error: Optional[Exception] = None
    for attempt in range(1, PLANNER_JSON_ATTEMPTS + 1):
        raw = await llm.complete(
            messages,
            system=PLANNER_SYSTEM,
            temperature=0.0,
            json_mode=True,
            model=settings.PLANNER_MODEL,
        )
        try:
            return llm.parse_json_object(raw)
        except ValueError as e:  # json.JSONDecodeError is a ValueError
            last_error = e
            logger.warning(f"Planner returned invalid JSON (attempt {attempt}/{PLANNER_JSON_ATTEMPTS}): {e}")
            messages = messages + [
                {"role": "assistant", "content": (raw or "")[:4000]},
                {"role": "user", "content": (
                    f"That reply was not valid JSON ({e}). Reply again with ONLY one valid JSON object "
                    "in the required shape. Escape any double quotes inside strings as \\\" and do not "
                    "add text before or after the object."
                )},
            ]
    raise ValueError(f"Planner JSON invalid after {PLANNER_JSON_ATTEMPTS} attempts: {last_error}")


SMALL_TALK = re.compile(
    r"^\s*(hi|hello|hey|hii+|thanks?|thank you|thx|ok(ay)?|bye|good (morning|afternoon|evening|night)|"
    r"how are you|who are you|what can you do)\b[\s!.?]*$",
    re.IGNORECASE,
)


def is_small_talk(query: str) -> bool:
    return bool(SMALL_TALK.match(query or ""))


async def has_enabled_documents() -> bool:
    try:
        async with db_manager.acquire() as conn:
            return bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM uploaded_files WHERE is_enabled)"))
    except Exception as e:
        logger.warning(f"Could not check for enabled documents: {e}")
        return False


async def llm_plan_step(
    messages: List[BaseMessage],
    application_id: int = 1,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Plan the next tool calls with the LLM, using conversation context and prior results."""
    if not mcp_manager.discovered_tools:
        try:
            await mcp_manager.discover_tools()
        except Exception as e:
            logger.warning(f"MCP discovery failed during planning: {e}")

    query = str(messages[-1].content) if messages else ""
    history = history or []

    completed = ""
    if history:
        completed = "\n\nActions completed so far:\n" + "\n".join(
            f"- {h.get('tool_name')}({json.dumps(h.get('arguments', {}), default=str)}) "
            f"[{h.get('status')}]:\n" + wrap_untrusted(str(h.get("tool_name")), str(h.get("output", ""))[:400])
            for h in history
        )

    conversation = _history_as_text(messages)
    prompt = (
        f"Tool catalog:\n{_tools_catalog()}\n\n"
        + (f"Conversation so far:\n{conversation}\n\n" if conversation else "")
        + f"Latest user message: {query}"
        + completed
        + "\n\nRespond ONLY with a JSON object of this shape:\n"
        '{"thought": "brief reason for the decision", '
        '"standalone_query": "the latest message rewritten so it is understandable without the conversation", '
        '"tool_calls": [{"tool": "exact_tool_name", "arguments": {}}]}'
    )

    if llm.active_provider():
        try:
            parsed = await _plan_with_retry(prompt)
            thought = str(parsed.get("thought") or "Planning next step.")
            standalone = str(parsed.get("standalone_query") or query).strip() or query

            known = set(mcp_manager.discovered_tools) | {KNOWLEDGE_TOOL}
            already_run = {_call_signature(h["tool_name"], h.get("arguments", {})) for h in history}
            calls: List[Dict[str, Any]] = []
            seen = set()
            kb_searches = sum(1 for h in history if h.get("tool_name") == KNOWLEDGE_TOOL)
            raw_calls = parsed.get("tool_calls") or []
            if not raw_calls and parsed.get("tool") not in (None, "", "none"):
                raw_calls = [{"tool": parsed.get("tool"), "arguments": parsed.get("arguments", {})}]

            for item in raw_calls[:MAX_TOOLS_PER_STEP]:
                if not isinstance(item, dict):
                    continue
                tool = re.sub(r"\(.*\)$", "", str(item.get("tool", ""))).strip()
                if tool not in known:
                    logger.warning(f"Planner chose unknown tool '{tool}'; ignoring.")
                    continue
                args = prepare_arguments(tool, item.get("arguments"), standalone, application_id)
                sig = _call_signature(tool, args)
                if sig in already_run or sig in seen:
                    continue
                if tool == KNOWLEDGE_TOOL and kb_searches >= MAX_KB_SEARCHES_PER_TURN:
                    # Reworded re-searches rarely add evidence but cost a model call each
                    logger.info("Knowledge search cap reached for this turn; skipping re-search.")
                    continue
                if tool == KNOWLEDGE_TOOL:
                    kb_searches += 1
                seen.add(sig)
                calls.append({
                    "call_id": f"call_{'rag' if tool == KNOWLEDGE_TOOL else 'mcp'}_{time.time_ns()}_{len(calls)}",
                    "name": tool,
                    "arguments": args,
                })
            return thought, calls
        except Exception as e:
            logger.warning(f"LLM planner failed ({e}), falling back to heuristic planner")

    # Heuristic fallback only decides the first step; later steps just answer.
    if history:
        return "Proceeding to answer with the evidence gathered.", []

    needs_kb, matched_hint = await check_internal_search_needed(query)
    reason = "User query relates to internal documentation, meeting notes, or uploaded files."
    if not needs_kb and not is_small_talk(query) and await has_enabled_documents():
        # The keyword rules can't recognise every company-specific question (e.g. "When does
        # the X banner appear?"). A search is cheap and harmless when nothing matches, while
        # skipping it means a confident answer that ignores the user's own documents.
        needs_kb = True
        reason = "AI planner unavailable; documents are available, so searching them before answering."
    if needs_kb:
        search_query = f"{query} {matched_hint}" if matched_hint else query
        return (
            f"{reason} Dispatching knowledge base search tool.",
            [{
                "call_id": f"call_rag_{time.time_ns()}",
                "name": KNOWLEDGE_TOOL,
                "arguments": {"query": search_query, "application_id": application_id},
            }],
        )

    return "General or conceptual inquiry. Answering directly without external tools.", []


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Analyzes the conversation and determines the plan and necessary tool calls."""
    messages = list(state["messages"])
    last_user_msg = str(messages[-1].content) if messages else ""
    current_iteration = state.get("iteration_count", 0) + 1
    existing_queue = state.get("tool_calls_queue", [])

    if existing_queue:
        queued_tools = existing_queue
        full_thought = f"Iteration {current_iteration}: Executing next step tool: {', '.join(t['name'] for t in queued_tools)}"
    elif current_iteration == 1:
        thought, queued_tools = await llm_plan_step(messages, state.get("application_id", 1))
        full_thought = f"Iteration {current_iteration}: {thought}"
    else:
        full_thought = f"Iteration {current_iteration}: Reflection complete. Proceeding with synthesis."
        queued_tools = []

    return {
        "iteration_count": current_iteration,
        "plan": f"Plan: {'Execute tools ' + ', '.join(t['name'] for t in queued_tools) if queued_tools else 'Direct synthesis'} for '{last_user_msg}'",
        "tool_calls_queue": queued_tools,
        "intermediate_thoughts": [_thought(current_iteration, full_thought)],
        "status": "executing_tools" if queued_tools else "answering"
    }


async def tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """Executes all queued tool calls concurrently with per-tool timeout protection."""
    queue = state.get("tool_calls_queue", [])
    if not queue:
        return {"status": "reflecting"}

    # Tools that can change things are never run by the agent itself: they are stored
    # as pending approvals and shown to the user, who decides in the chat.
    runnable, held = [], []
    for call in queue:
        if call["name"].startswith("mcp_") and mcp_manager.requires_approval(call["name"]):
            held.append(call)
        else:
            runnable.append(call)

    records, new_citations = await execute_tools_parallel(runnable) if runnable else ([], [])

    for call in held:
        try:
            approval_id = await create_pending_approval(
                state.get("session_id", ""), state.get("user_id", ""), call["name"], call["arguments"],
                reason=str(state["messages"][-1].content)[:500] if state.get("messages") else None,
            )
            records.append({
                "call_id": call["call_id"],
                "tool_name": call["name"],
                "arguments": call["arguments"],
                "output": "NOT EXECUTED: this action changes data and is waiting for the user's approval.",
                "latency_ms": 0.0,
                "status": "pending_approval",
                "approval_id": approval_id,
            })
        except Exception as e:
            logger.error(f"Could not create approval request for {call['name']}: {e}")
            records.append({
                "call_id": call["call_id"],
                "tool_name": call["name"],
                "arguments": call["arguments"],
                "output": f"NOT EXECUTED: the approval request could not be created ({e}).",
                "latency_ms": 0.0,
                "status": "error",
            })

    # tool_execution_history and citations use an `operator.add` reducer, so only the
    # NEW items are returned; returning old + new would duplicate every earlier entry.
    return {
        "tool_calls_queue": [],
        "tool_execution_history": records,
        "citations": new_citations,
        "status": "reflecting"
    }


async def reflection_node(state: AgentState) -> Dict[str, Any]:
    """Reflects on tool outputs and determines whether to loop or synthesize the final answer."""
    iteration = state.get("iteration_count", 1)
    history = state.get("tool_execution_history", [])
    messages = list(state.get("messages", []))

    if any(h.get("status") == "pending_approval" for h in history):
        return {
            "intermediate_thoughts": [_thought(iteration + 1, "An action needs the user's approval before it can run. Pausing and asking the user.")],
            "status": "answering"
        }

    if iteration >= settings.MAX_AGENT_ITERATIONS or not history:
        return {
            "intermediate_thoughts": [_thought(iteration + 1, "Evaluation complete. Evidence analyzed, proceeding to synthesize comprehensive answer.")],
            "status": "answering"
        }

    try:
        thought, next_tools = await llm_plan_step(messages, state.get("application_id", 1), history=history)
        if next_tools:
            return {
                "tool_calls_queue": next_tools,
                "intermediate_thoughts": [_thought(iteration + 1, f"Reflection: Additional action needed -> {thought}")],
                "status": "planning"
            }
    except Exception as e:
        logger.warning(f"Reflection follow-up evaluation failed ({e}), proceeding to answer.")

    return {
        "intermediate_thoughts": [_thought(iteration + 1, "Evaluation complete. Sufficient evidence gathered, proceeding to synthesize answer.")],
        "status": "answering"
    }


ANSWER_SYSTEM = (
    "You are an intelligent, helpful enterprise AI assistant.\n"
    "- If internal documentation or tool output is provided, prioritize it and cite facts accurately "
    "using the [n] source numbers where available.\n"
    "- If the user asks a general knowledge, conceptual, or conversational question, answer it clearly "
    "and thoroughly using your broad general knowledge.\n"
    "- If internal context was searched but nothing relevant was found, answer helpfully from general "
    "knowledge and say that no specific internal document matched.\n"
    "- If a tool returned an error, explain it briefly and plainly.\n"
    f"- {UNTRUSTED_DATA_RULE}"
)


def _get_writer():
    try:
        from langgraph.config import get_stream_writer
        return get_stream_writer()
    except Exception:
        return lambda _chunk: None


def _offline_answer(query: str, passages: str) -> str:
    query_lower = query.lower().strip()
    if query_lower in ["hi", "hello", "hey", "greetings"]:
        return (
            "Hello! 👋 I am your autonomous enterprise AI assistant. You can ask me:\n\n"
            "- **General questions** (e.g., definitions, technology explainers, coding)\n"
            "- **Company policies & documentation** (via our Knowledge Base)\n"
            "- **Tool operations** (via Model Context Protocol - MCP)\n\n"
            "How can I assist you today?"
        )
    if passages:
        return (
            f"Based on internal knowledge base documentation:\n\n{passages[:800]}...\n\n"
            "Please review the attached source citations for full details."
        )
    return (
        f"### Query Received: *\"{query}\"*\n\n"
        "No language model is available right now (no API key configured, or every model call failed).\n\n"
        "**To enable live answers:**\n"
        "1. Open `.env` in the project root directory.\n"
        "2. Set `GEMINI_API_KEY=...` or `OPENAI_API_KEY=...`\n"
        "3. Restart the backend container (`docker compose up -d backend`).\n\n"
        "You can still upload documents in the **Knowledge Studio** tab."
    )


async def answer_node(state: AgentState) -> Dict[str, Any]:
    """Synthesizes the final answer, streaming tokens to the client as they are generated."""
    history = state.get("tool_execution_history", [])
    messages = list(state["messages"])
    last_user_msg = str(messages[-1].content) if messages else ""

    evidence = [
        wrap_untrusted(h["tool_name"], str(h["output"])[:MAX_TOOL_OUTPUT_CHARS])
        for h in history
        if h["status"] == "success" and "No matching documents" not in str(h["output"])
    ]
    errors = [f"{h['tool_name']}: {str(h['output'])[:300]}" for h in history if h["status"] not in ("success", "pending_approval")]
    pending = [
        f"{h['tool_name']} with arguments {json.dumps(h.get('arguments', {}), default=str)[:400]}"
        for h in history if h["status"] == "pending_approval"
    ]
    passages = "\n\n".join(evidence)
    raw_passages = "\n\n".join(
        str(h["output"]) for h in history
        if h["status"] == "success" and "No matching documents" not in str(h["output"])
    )

    user_content = (
        f"Context:\n{passages if passages else 'None'}\n\n"
        + (f"Tool errors:\n" + "\n".join(errors) + "\n\n" if errors else "")
        + ("Actions prepared but NOT executed (waiting for the user's approval):\n" + "\n".join(pending)
           + "\nTell the user exactly what each action will do and ask them to press Approve or Reject on "
             "the approval card below. Do NOT say the action was done.\n\n" if pending else "")
        + f"User Question: {last_user_msg}"
    )
    llm_messages = _history_as_messages(messages) + [{"role": "user", "content": user_content}]

    writer = _get_writer()
    parts: List[str] = []

    if llm.active_provider():
        try:
            async for text in llm.stream(llm_messages, system=ANSWER_SYSTEM):
                parts.append(text)
                writer({"type": "token", "text": text})
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            if parts:
                note = "\n\n⚠️ *The response was interrupted before it finished.*"
                parts.append(note)
                writer({"type": "token", "text": note})

    final_text = "".join(parts)
    if not final_text:
        final_text = _offline_answer(last_user_msg, raw_passages)
        writer({"type": "token", "text": final_text})

    return {"final_answer": final_text, "status": "completed"}
