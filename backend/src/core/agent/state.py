"""LangGraph Agent State and Trace Definitions."""
from typing import Annotated, Sequence, TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage
import operator
from datetime import datetime

class ToolCallRecord(TypedDict):
    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    output: Any
    latency_ms: float
    status: str  # "success" | "error" | "timeout"

class CitationRecord(TypedDict):
    document_name: str
    section_title: Optional[str]
    snippet: str
    confidence_score: float
    chunk_id: str

class ThoughtStepRecord(TypedDict): 
    step: int
    thought: str
    timestamp: str

class AgentState(TypedDict):
    session_id: str
    application_id: int
    application_name: str
    messages: Annotated[Sequence[BaseMessage], operator.add]
    plan: Optional[str]
    iteration_count: int
    tool_calls_queue: List[Dict[str, Any]]
    tool_execution_history: Annotated[List[ToolCallRecord], operator.add]
    citations: Annotated[List[CitationRecord], operator.add]
    intermediate_thoughts: Annotated[List[ThoughtStepRecord], operator.add]
    final_answer: Optional[str]
    status: str  # "planning" | "executing_tools" | "reflecting" | "answering" | "error"
