"""Approval gate: which tools need approval, and that the agent never runs them itself."""
import pytest

from src.config import settings
from src.core.agent import nodes
from src.core.mcp.manager import MCPClientManager


def _manager_with(tools: dict) -> MCPClientManager:
    m = MCPClientManager(config_path="does-not-exist.json")
    m.discovered_tools = tools
    return m


def _tool(name, annotations=None, config=None):
    return {
        "server_name": "srv",
        "tool_name": name,
        "original_tool": {"name": name, **({"annotations": annotations} if annotations is not None else {})},
        "config": config or {},
    }


def test_read_only_tools_run_without_approval():
    m = _manager_with({"mcp_srv_get_me": _tool("get_me", {"readOnlyHint": True})})
    assert m.requires_approval("mcp_srv_get_me") is False


@pytest.mark.parametrize("annotations", [{"readOnlyHint": False}, {"destructiveHint": True}, {}, None])
def test_write_or_unannotated_tools_need_approval(annotations):
    m = _manager_with({"mcp_srv_delete_file": _tool("delete_file", annotations)})
    assert m.requires_approval("mcp_srv_delete_file") is True


def test_unknown_tools_need_approval():
    assert _manager_with({}).requires_approval("mcp_srv_whatever") is True


def test_config_auto_approve_list_and_all():
    m = _manager_with({
        "mcp_srv_a": _tool("a", {}, {"auto_approve": ["a"]}),
        "mcp_srv_b": _tool("b", {}, {"auto_approve": "all"}),
        "mcp_srv_c": _tool("c", {}, {"auto_approve": ["a"]}),
    })
    assert m.requires_approval("mcp_srv_a") is False
    assert m.requires_approval("mcp_srv_b") is False
    assert m.requires_approval("mcp_srv_c") is True


def test_global_switch_disables_gate(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_APPROVAL_REQUIRED", False)
    assert _manager_with({}).requires_approval("mcp_srv_x") is False


async def test_executor_holds_write_tools_and_runs_read_tools(monkeypatch):
    from langchain_core.messages import HumanMessage

    executed = []

    async def fake_exec(queue):
        executed.extend(c["name"] for c in queue)
        return [{"call_id": c["call_id"], "tool_name": c["name"], "arguments": c["arguments"],
                 "output": "ok", "latency_ms": 1.0, "status": "success"} for c in queue], []

    created = []

    async def fake_create(session_id, user_id, tool_name, arguments, reason):
        created.append((session_id, user_id, tool_name, arguments))
        return "approval-123"

    monkeypatch.setattr(nodes, "execute_tools_parallel", fake_exec)
    monkeypatch.setattr(nodes, "create_pending_approval", fake_create)
    monkeypatch.setattr(nodes.mcp_manager, "requires_approval", lambda name: "delete" in name)

    state = {
        "session_id": "s1",
        "user_id": "u1",
        "messages": [HumanMessage(content="delete the old file and show my profile")],
        "tool_calls_queue": [
            {"call_id": "c1", "name": "mcp_gh_get_me", "arguments": {}},
            {"call_id": "c2", "name": "mcp_gh_delete_file", "arguments": {"path": "old.txt"}},
        ],
    }
    out = await nodes.tool_executor_node(state)

    assert executed == ["mcp_gh_get_me"]  # the delete never reached the executor
    assert created == [("s1", "u1", "mcp_gh_delete_file", {"path": "old.txt"})]
    held = [r for r in out["tool_execution_history"] if r["status"] == "pending_approval"]
    assert len(held) == 1 and held[0]["approval_id"] == "approval-123"


async def test_reflection_stops_when_an_action_awaits_approval():
    out = await nodes.reflection_node({
        "iteration_count": 1,
        "messages": [],
        "tool_execution_history": [{"tool_name": "t", "status": "pending_approval", "arguments": {}, "output": ""}],
    })
    assert out["status"] == "answering"
