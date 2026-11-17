"""Agent node behaviour and MCP client/server protocol handling."""
import sys
from pathlib import Path

import pytest

from src.core import llm
from src.core.agent import nodes
from src.core.mcp.manager import MCPClientManager, StdioSession

REPO_ROOT = Path(__file__).resolve().parents[2].parent
sys.path.insert(0, str(REPO_ROOT if (REPO_ROOT / "mcp_servers").exists() else Path.cwd()))


def test_parse_json_object_handles_fences_and_prose():
    assert llm.parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json_object('Sure! {"tool_calls": []} hope that helps') == {"tool_calls": []}
    # Two concatenated objects: the first one wins
    assert llm.parse_json_object('{"thought": "a", "tool_calls": []}{"thought": "b"}')["thought"] == "a"


def test_prepare_arguments_forces_application_scope():
    args = nodes.prepare_arguments(
        "knowledge_base_search", {"query": "", "application_id": 999}, "leave policy", application_id=2
    )
    assert args == {"query": "leave policy", "application_id": 2}


def test_prepare_arguments_keeps_model_arguments_for_mcp_tools():
    args = nodes.prepare_arguments("mcp_github_search_code", {"query": "repo:x foo"}, "q", 1)
    assert args == {"query": "repo:x foo"}


async def test_tool_executor_returns_only_new_records(monkeypatch):
    new_record = {"call_id": "c2", "tool_name": "t", "arguments": {}, "output": "x",
                  "latency_ms": 1.0, "status": "success"}

    async def fake_exec(queue):
        return [new_record], [{"chunk_id": "n"}]

    monkeypatch.setattr(nodes, "execute_tools_parallel", fake_exec)
    state = {
        "tool_calls_queue": [{"call_id": "c2", "name": "t", "arguments": {}}],
        "tool_execution_history": [{"call_id": "c1"}],
        "citations": [{"chunk_id": "old"}],
    }
    out = await nodes.tool_executor_node(state)
    # The graph reducer appends these; returning old items too would duplicate them.
    assert out["tool_execution_history"] == [new_record]
    assert out["citations"] == [{"chunk_id": "n"}]


async def test_answer_node_falls_back_without_llm(monkeypatch):
    from langchain_core.messages import HumanMessage

    monkeypatch.setattr(llm, "active_provider", lambda: None)
    out = await nodes.answer_node({"messages": [HumanMessage(content="hello")], "tool_execution_history": []})
    assert out["status"] == "completed"
    assert "Hello" in out["final_answer"]


def test_parse_sse_response_picks_matching_id():
    body = (
        'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
        'event: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n\n'
    )
    assert MCPClientManager._parse_mcp_response(body, 7)["result"] == {"ok": True}


def test_filesystem_server_blocks_path_traversal():
    from mcp_servers.filesystem.server import handle_request

    resp = handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "read_staged_file", "arguments": {"filename": "../../.env"}},
    })
    assert resp["result"]["isError"] is True
    assert "not allowed" in resp["result"]["content"][0]["text"]


def test_filesystem_server_supports_initialize():
    from mcp_servers.filesystem.server import handle_request

    resp = handle_request({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    assert resp["result"]["capabilities"] == {"tools": {}}


async def test_stdio_session_handshake_and_reuse():
    session = StdioSession("fs", {"command": sys.executable, "args": ["-m", "mcp_servers.filesystem.server"]})
    try:
        tools = await session.request("tools/list", {}, timeout=15)
        first_pid = session.proc.pid
        names = {t["name"] for t in tools["tools"]}
        assert {"list_staging_files", "read_staged_file"} <= names
        # Second request reuses the same long-lived process
        await session.request("tools/list", {}, timeout=15)
        assert session.proc.pid == first_pid
    finally:
        await session.close()


async def test_planner_caps_reworded_knowledge_searches(monkeypatch):
    from langchain_core.messages import HumanMessage

    async def fake_complete(*args, **kwargs):
        return '{"thought": "search again", "standalone_query": "q", ' \
               '"tool_calls": [{"tool": "knowledge_base_search", "arguments": {"query": "yet another wording"}}]}'

    monkeypatch.setattr(llm, "active_provider", lambda: "gemini")
    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(nodes.mcp_manager, "discovered_tools", {"mcp_x_y": {"original_tool": {}}})
    history = [
        {"tool_name": "knowledge_base_search", "arguments": {"query": f"q{i}", "application_id": 1},
         "status": "success", "output": "passages"}
        for i in range(nodes.MAX_KB_SEARCHES_PER_TURN)
    ]
    _, calls = await nodes.llm_plan_step([HumanMessage(content="q")], 1, history=history)
    assert calls == []
