"""MCP Tool Schema to OpenAI/Gemini Function Definition Adapter."""
from typing import Dict, Any

def mcp_to_openai_tool(server_name: str, mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
    """Translate an MCP tool definition into an OpenAI function calling schema."""
    tool_name = f"mcp_{server_name}_{mcp_tool['name']}"
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": f"[{server_name}] {mcp_tool.get('description', '')}",
            "parameters": mcp_tool.get("inputSchema", {
                "type": "object",
                "properties": {},
            })
        }
    }
