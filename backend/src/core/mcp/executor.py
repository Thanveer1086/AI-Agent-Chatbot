"""Parallel Tool Execution Engine."""
import asyncio
import json
import time
import logging
from typing import List, Dict, Any, Tuple
from src.core.mcp.manager import mcp_manager
from src.core.rag.tool import search_knowledge_base
from src.core.agent.state import ToolCallRecord

logger = logging.getLogger(__name__)

async def execute_single_tool(call_id: str, tool_name: str, arguments: Dict[str, Any]) -> Tuple[ToolCallRecord, List[Dict[str, Any]]]:
    """Execute either internal knowledge search or an external MCP tool."""
    start_time = time.time()
    citations = []

    try:
        if tool_name == "knowledge_base_search":
            res = await search_knowledge_base(**arguments)
            latency = (time.time() - start_time) * 1000
            citations = res.get("citations", [])
            record: ToolCallRecord = {
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "output": res.get("passages"),
                "latency_ms": round(latency, 2),
                "status": "success"
            }
            return record, citations
        elif tool_name.startswith("mcp_"):
            res = await mcp_manager.execute_tool(tool_name, arguments)
            latency = (time.time() - start_time) * 1000
            content = res.get("content", [])
            texts = [c.get("text", "") for c in (content or []) if isinstance(c, dict) and c.get("type", "text") == "text"]
            if not texts and res.get("structuredContent") is not None:
                texts = [json.dumps(res["structuredContent"], default=str)]
            output_text = "\n".join(texts) if texts else res.get("error", "Executed (no text output).")
            is_error = res.get("isError", False) or "error" in res
            record: ToolCallRecord = {
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "output": output_text,
                "latency_ms": round(latency, 2),
                "status": "error" if is_error else "success"
            }
            return record, citations
        else:
            latency = (time.time() - start_time) * 1000
            record: ToolCallRecord = {
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "output": f"Unknown tool: {tool_name}",
                "latency_ms": round(latency, 2),
                "status": "error"
            }
            return record, citations
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.error(f"Execution error on tool {tool_name}: {e}")
        record: ToolCallRecord = {
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "output": f"Exception: {str(e)}",
            "latency_ms": round(latency, 2),
            "status": "error"
        }
        return record, citations

async def execute_tools_parallel(tool_calls: List[Dict[str, Any]]) -> Tuple[List[ToolCallRecord], List[Dict[str, Any]]]:
    """Execute multiple independent tool calls concurrently via asyncio.gather."""
    tasks = [
        execute_single_tool(call["call_id"], call["name"], call["arguments"])
        for call in tool_calls
    ]
    results = await asyncio.gather(*tasks)

    all_records = []
    all_citations = []
    for record, citations in results:
        all_records.append(record)
        all_citations.extend(citations)

    return all_records, all_citations
