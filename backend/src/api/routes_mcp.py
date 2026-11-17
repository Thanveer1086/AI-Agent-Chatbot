"""Model Context Protocol (MCP) Management & Health Endpoints."""
import logging
from fastapi import APIRouter, Depends
from src.core.security.auth import get_current_user, require_admin, UserClaims
from src.core.mcp.manager import mcp_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mcp", tags=["MCP Tools & Servers"])

@router.get("/servers")
async def list_mcp_servers_endpoint(
    user: UserClaims = Depends(get_current_user)
):
    """List configured MCP servers and their transport status."""
    servers_info = []
    for name, cfg in mcp_manager.servers.items():
        enabled = cfg.get("enabled", True)
        tools_for_server = [
            t for t in mcp_manager.discovered_tools.values()
            if t["server_name"] == name
        ]
        servers_info.append({
            "name": name,
            "transport": cfg.get("transport") or ("http" if cfg.get("url") else "stdio"),
            "status": "online" if enabled else "offline",
            "tool_count": len(tools_for_server)
        })

    return {"servers": servers_info}

@router.get("/tools")
async def list_mcp_tools_endpoint(
    user: UserClaims = Depends(get_current_user)
):
    """List all dynamically discovered MCP tools with their input schemas."""
    # Ensure tools have been discovered at least once
    if not mcp_manager.discovered_tools:
        await mcp_manager.discover_tools()

    tool_list = []
    for full_name, t in mcp_manager.discovered_tools.items():
        orig = t["original_tool"]
        tool_list.append({
            "server_name": t["server_name"],
            "tool_name": orig["name"],
            "full_name": full_name,
            "description": orig.get("description", ""),
            "input_schema": orig.get("inputSchema", {}),
            "transport": t["config"].get("transport") or ("http" if t["config"].get("url") else "stdio"),
            "is_active": True
        })

    return {"tools": tool_list}

@router.post("/reload")
async def reload_mcp_tools_endpoint(
    user: UserClaims = Depends(require_admin)
):
    """Trigger runtime re-discovery across all configured MCP servers."""
    tools = await mcp_manager.discover_tools()
    return {
        "success": True,
        "message": f"Successfully reloaded MCP tools. Discovered {len(tools)} tools.",
        "tool_count": len(tools)
    }
