"""LangGraph Nodes: Planner, Tool Executor, Reflection, and Synthesizer."""
import time
import json
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.core.agent.state import AgentState, ToolCallRecord, ThoughtStepRecord
from src.core.rag.tool import search_knowledge_base, KNOWLEDGE_TOOL_SCHEMA
from src.core.mcp.executor import execute_tools_parallel
from src.core.mcp.manager import mcp_manager
from src.config import settings

logger = logging.getLogger(__name__)

import difflib
from src.core.db.session import db_manager

# Keywords indicating intent for internal company knowledge, meetings, or uploaded documents
INTERNAL_INTENT_PATTERNS = [
    r"\b(meeting|sync|transcript|notes|minutes|agenda|discussion|summary|summarize|action items|takeaway|takeaways|brief|recording)\b",
    r"\b(policy|handbook|reimburse|expense|benefit|vacation|leave|ticket|guideline|contract|procedure|rule|uploaded|attachment|company|internal|doc|docx|pdf|guide|spec|specification|report|project|review|overview|details|explanation)\b",
    r"\b(our\s+[a-z]+|my\s+(team|manager|leave|policy|expense|salary|benefit)|hr\b|it support)\b"
]

async def check_internal_search_needed(query: str):
    """Determine if query is targeted at internal company documents, meetings, or uploaded files."""
    query_lower = query.lower().strip()

    for pattern in INTERNAL_INTENT_PATTERNS:
        if re.search(pattern, query_lower):
            return True, None

    try:
        async with db_manager.acquire() as conn:
            rows = await conn.fetch("SELECT filename FROM uploaded_files WHERE is_enabled = TRUE;")
            file_names = [r["filename"] for r in rows]
            query_words = [w for w in re.findall(r"[a-zA-Z0-9_-]+", query_lower) if len(w) >= 3]
            for fname in file_names:
                clean_fname = re.sub(r"\.[a-zA-Z0-9]+$", "", fname).lower()
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

async def llm_plan_step(query: str, application_id: int = 1, history: Optional[List[Dict[str, Any]]] = None):
    """Dynamically plan tools using LLM reasoning over all discovered MCP tools and RAG."""
    if not mcp_manager.discovered_tools:
        await mcp_manager.discover_tools()

    tools_doc = [
        "- knowledge_base_search(query): Searches internal company documents, meeting notes/recordings, transcripts, policies, specifications, and uploaded files in the vector database."
    ]
    for full_name, t in mcp_manager.discovered_tools.items():
        orig = t.get("original_tool", {})
        desc = orig.get("description", "Execute tool")
        req_params = orig.get("inputSchema", {}).get("required", [])
        params_str = f"({', '.join(req_params)})" if req_params else "()"
        tools_doc.append(f"- {full_name}{params_str}: {desc[:140]}")

    tools_prompt = "\n".join(tools_doc)

    history_context = ""
    if history:
        history_summary = []
        for h in history:
            output_snippet = str(h.get("output", ""))[:180]
            history_summary.append(f"- Tool '{h.get('tool_name')}' result: {output_snippet}")
        history_context = "\nActions Completed So Far:\n" + "\n".join(history_summary) + "\n"

    prompt = f"""You are an autonomous AI Agent Planner.
Analyze the user's inquiry and the actions completed so far.
Select the single next best tool to call, or 'none' if you have sufficient information to answer the user query directly.

Available Tools:
{tools_prompt}
{history_context}
User Query: "{query}"

Respond ONLY with a JSON object:
{{
  "tool": "exact_tool_name_or_none",
  "arguments": {{}},
  "thought": "Brief explanation of your decision for this step"
}}
"""
    if settings.GEMINI_API_KEY:
        try:
            import asyncio
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3.5-flash-lite",
                contents=prompt
            )
            raw = resp.text.strip()
            if "```" in raw:
                raw = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw).group(1)
            parsed = json.loads(raw)
            tool = parsed.get("tool", "none").strip()
            tool = re.sub(r"\(.*\)$", "", tool).strip()
            thought = parsed.get("thought", f"Planned action: {tool}")
            arguments = parsed.get("arguments", {})

            if tool and tool != "none":
                default_user = mcp_manager.authenticated_user or getattr(settings, "GITHUB_USERNAME", "Thanveer1086")
                if tool == "knowledge_base_search":
                    if "query" not in arguments:
                        arguments["query"] = query
                    arguments["application_id"] = application_id
                elif "search_repositories" in tool and not arguments.get("query"):
                    arguments["query"] = f"user:{default_user}"
                elif "search_" in tool and "query" not in arguments:
                    arguments["query"] = f"user:{default_user}"
                    
                call_id = f"call_{'rag' if tool == 'knowledge_base_search' else 'mcp'}_{int(time.time()*1000)}"
                return thought, [{
                    "call_id": call_id,
                    "name": tool,
                    "arguments": arguments
                }]
            else:
                return thought, []
        except Exception as e:
            logger.warning(f"LLM planner failed ({e}), falling back to heuristic planner")

    # Fallback heuristic if LLM planner fails or no API key
    needs_kb, matched_hint = await check_internal_search_needed(query)
    if needs_kb:
        search_query = f"{query} {matched_hint}" if matched_hint else query
        thought = (
            f"User query relates to internal documentation, meeting notes, or uploaded files. "
            "Dispatching knowledge base search tool."
        )
        return thought, [{
            "call_id": f"call_rag_{int(time.time()*1000)}",
            "name": "knowledge_base_search",
            "arguments": {
                "query": search_query,
                "application_id": application_id
            }
        }]

    return "General or conceptual inquiry. Answering directly using comprehensive knowledge without requiring external tools.", []

async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Analyzes the latest user message and determines the plan and necessary tool calls."""
    messages = state["messages"]
    last_user_msg = messages[-1].content if messages else ""
    current_iteration = state.get("iteration_count", 0) + 1
    existing_queue = state.get("tool_calls_queue", [])

    if existing_queue:
        queued_tools = existing_queue
        full_thought = f"Iteration {current_iteration}: Executing next step tool: {', '.join([t['name'] for t in queued_tools])}"
    elif current_iteration == 1:
        thought, queued_tools = await llm_plan_step(last_user_msg, state.get("application_id", 1))
        full_thought = f"Iteration {current_iteration}: {thought}"
    else:
        full_thought = f"Iteration {current_iteration}: Reflection complete. Proceeding with synthesis."
        queued_tools = []

    thought_record: ThoughtStepRecord = {
        "step": current_iteration,
        "thought": full_thought,
        "timestamp": datetime.utcnow().isoformat()
    }

    return {
        "iteration_count": current_iteration,
        "plan": f"Plan: {'Execute tools ' + ', '.join([t['name'] for t in queued_tools]) if queued_tools else 'Direct synthesis'} for '{last_user_msg}'",
        "tool_calls_queue": queued_tools,
        "intermediate_thoughts": [thought_record],
        "status": "executing_tools" if queued_tools else "answering"
    }

async def tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """Executes all queued tool calls concurrently with per-tool timeout protection."""
    queue = state.get("tool_calls_queue", [])
    if not queue:
        return {"status": "reflecting"}

    records, new_citations = await execute_tools_parallel(queue)
    existing_history = state.get("tool_execution_history", [])
    existing_citations = state.get("citations", [])

    return {
        "tool_calls_queue": [],
        "tool_execution_history": existing_history + records,
        "citations": existing_citations + new_citations,
        "status": "reflecting"
    }

async def reflection_node(state: AgentState) -> Dict[str, Any]:
    """Reflects on tool outputs and determines whether to loop or synthesize the final answer."""
    iteration = state.get("iteration_count", 1)
    history = state.get("tool_execution_history", [])
    messages = state.get("messages", [])
    last_user_msg = messages[-1].content if messages else ""

    # If reached max iteration limit or no history, finalize
    if iteration >= settings.MAX_AGENT_ITERATIONS or not history:
        thought_record: ThoughtStepRecord = {
            "step": iteration + 1,
            "thought": "Evaluation complete. Evidence analyzed, proceeding to synthesize comprehensive answer.",
            "timestamp": datetime.utcnow().isoformat()
        }
        return {
            "intermediate_thoughts": [thought_record],
            "status": "answering"
        }

    # Evaluate whether a follow-up tool is needed
    try:
        thought, next_tools = await llm_plan_step(last_user_msg, state.get("application_id", 1), history=history)
        if next_tools:
            thought_record: ThoughtStepRecord = {
                "step": iteration + 1,
                "thought": f"Reflection: Additional action needed -> {thought}",
                "timestamp": datetime.utcnow().isoformat()
            }
            return {
                "tool_calls_queue": next_tools,
                "intermediate_thoughts": [thought_record],
                "status": "planning"
            }
    except Exception as e:
        logger.warning(f"Reflection follow-up evaluation failed ({e}), proceeding to answer.")

    thought_record = {
        "step": iteration + 1,
        "thought": "Evaluation complete. Sufficient evidence gathered, proceeding to synthesize answer.",
        "timestamp": datetime.utcnow().isoformat()
    }
    return {
        "intermediate_thoughts": [thought_record],
        "status": "answering"
    }

async def answer_node(state: AgentState) -> Dict[str, Any]:
    """Synthesizes final answer from gathered evidence or general AI knowledge."""
    history = state.get("tool_execution_history", [])
    citations = state.get("citations", [])
    messages = state["messages"]
    last_user_msg = messages[-1].content if messages else ""

    # Synthesize context from any executed tools
    valid_passages = [str(h["output"]) for h in history if h["status"] == "success" and "No matching documents" not in str(h["output"])]
    passages = "\n\n".join(valid_passages)

    # Format multi-turn conversational history if present
    conversation_history_text = ""
    if len(messages) > 1:
        history_lines = []
        for m in messages[:-1]:
            sender = "User" if m.__class__.__name__ == "HumanMessage" else "Assistant"
            history_lines.append(f"{sender}: {m.content}")
        conversation_history_text = "Prior Conversation Context:\n" + "\n".join(history_lines) + "\n\n"

    final_text = ""

    # 1. Generate with OpenAI if configured
    if settings.OPENAI_API_KEY and (settings.API_USED == "openai" or not settings.GEMINI_API_KEY):
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            system_prompt = (
                "You are an intelligent, helpful enterprise AI assistant.\n"
                "- If relevant internal documentation or tool output is provided in the Context below, prioritize it and cite facts accurately.\n"
                "- If the user asks a general knowledge, conceptual, or conversational question, answer it clearly, thoroughly, and helpfully using your broad general knowledge.\n"
                "- If internal context was searched but no specific company documents were found, answer the question helpfully using general knowledge while clarifying that no specific internal company document was matched."
            )
            user_content = f"{conversation_history_text}Context:\n{passages if passages else 'None'}\n\nUser Question: {last_user_msg}"
            
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
            )
            final_text = resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI answer generation failed: {e}")

    # 2. Generate with Gemini if configured
    elif settings.GEMINI_API_KEY:
        try:
            import asyncio
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = (
                f"You are a helpful enterprise AI assistant.\n"
                f"{conversation_history_text}"
                f"- If internal context is provided, ground your response in it:\n{passages if passages else 'None'}\n"
                f"- Otherwise, answer the user's question accurately, thoroughly, and helpfully using general knowledge.\n\n"
                f"User Question: {last_user_msg}"
            )
            # Try available flash models in order of latency and availability
            candidate_models = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
            for m in candidate_models:
                try:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=m,
                        contents=prompt
                    )
                    if response and response.text:
                        final_text = response.text
                        break
                except Exception as model_err:
                    logger.warning(f"Gemini generation with {m} failed ({model_err}), trying next candidate...")
        except Exception as e:
            logger.error(f"Gemini answer generation failed: {e}")

    # 3. Intelligent fallback when no external LLM key is configured yet
    if not final_text:
        query_lower = last_user_msg.lower().strip()
        if "what is an ai" in query_lower or "what is ai" in query_lower or "artificial intelligence" in query_lower:
            final_text = (
                "**Artificial Intelligence (AI)** refers to the simulation of human intelligence in machines that are programmed to think, learn, and solve problems.\n\n"
                "### Core Branches of AI:\n"
                "1. **Machine Learning (ML)**: Algorithms that learn from data patterns to make predictions or decisions without explicit rule programming.\n"
                "2. **Deep Learning**: Multi-layered artificial neural networks capable of processing images, audio, video, and complex language representations.\n"
                "3. **Generative AI & LLMs**: Transformer-based models (such as GPT-4 and Gemini) capable of generating coherent text, code, images, and multimodal content.\n"
                "4. **Autonomous AI Agents**: Systems combining LLM reasoning, long-term memory, planning loops, and tool execution (like MCP tools and Vector RAG) to achieve goals autonomously.\n\n"
                "> 💡 *Tip: To enable live dynamic responses for any question, add your `OPENAI_API_KEY` or `GEMINI_API_KEY` to the `.env` file and restart.*"
            )
        elif query_lower in ["hi", "hello", "hey", "greetings"]:
            final_text = (
                "Hello! 👋 I am your autonomous enterprise AI assistant. You can ask me:\n\n"
                "- **General questions** (e.g., definitions, technology explainers, coding)\n"
                "- **Company policies & documentation** (via our Knowledge Base)\n"
                "- **Tool operations** (via Model Context Protocol - MCP)\n\n"
                "How can I assist you today?"
            )
        elif passages:
            final_text = (
                f"Based on internal knowledge base documentation:\n\n"
                f"{passages[:800]}...\n\n"
                f"Please review the attached source citations for full details."
            )
        else:
            final_text = (
                f"### Query Received: *\"{last_user_msg}\"*\n\n"
                "The chatbot is currently running without an external LLM API key configured in `.env`.\n\n"
                "**To enable live answers for all general and custom questions:**\n"
                "1. Open `.env` in the project root directory.\n"
                "2. Set your API key:\n"
                "   ```env\n"
                "   OPENAI_API_KEY=your_key_here\n"
                "   # or\n"
                "   GEMINI_API_KEY=your_key_here\n"
                "   ```\n"
                "3. Restart the backend container (`docker compose restart backend`).\n\n"
                "You can also upload PDFs/Word documents in the **Knowledge Base** tab to search internal documents!"
            )

    return {
        "final_answer": final_text,
        "status": "completed"
    }
