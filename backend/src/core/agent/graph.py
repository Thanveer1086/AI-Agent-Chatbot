"""LangGraph StateGraph Compilation & Workflow Construction."""
from langgraph.graph import StateGraph, END
from src.core.agent.state import AgentState
from src.core.agent.nodes import planner_node, tool_executor_node, reflection_node, answer_node

def should_execute_tools(state: AgentState) -> str:
    """Route to tool executor if tools are queued, else proceed to answering."""
    if state.get("tool_calls_queue"):
        return "tool_executor"
    return "answer"

def should_continue_loop(state: AgentState) -> str:
    """Route after reflection: loop back to planner or finalize answer."""
    status = state.get("status")
    if status == "planning":
        return "planner"
    return "answer"

def build_agent_graph():
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("answer", answer_node)

    # Set Entry Point
    workflow.set_entry_point("planner")

    # Add Edges & Conditional Routing
    workflow.add_conditional_edges(
        "planner",
        should_execute_tools,
        {
            "tool_executor": "tool_executor",
            "answer": "answer"
        }
    )

    workflow.add_edge("tool_executor", "reflection")

    workflow.add_conditional_edges(
        "reflection",
        should_continue_loop,
        {
            "planner": "planner",
            "answer": "answer"
        }
    )

    workflow.add_edge("answer", END)

    return workflow.compile()

# Global compiled agent instance
agent_app = build_agent_graph()
