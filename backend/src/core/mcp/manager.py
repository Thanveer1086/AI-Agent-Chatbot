"""Model Context Protocol (MCP) Client Manager."""
import json
import re
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.core.mcp.adapters import mcp_to_openai_tool
from src.config import settings

logger = logging.getLogger(__name__)

class MCPClientManager:
    def __init__(self, config_path: str = "mcp_config.json", cache_path: str = "storage/mcp_tools_cache.json"):
        self.config_path = Path(config_path)
        self.cache_path = Path(cache_path)
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.discovered_tools: Dict[str, Dict[str, Any]] = {}
        self.authenticated_user: Optional[str] = getattr(settings, "GITHUB_USERNAME", "Thanveer1086")
        self._load_config()

    def _load_config(self):
        """Read mcp_config.json with environment variable substitution support (${VAR_NAME})."""
        if not self.config_path.exists():
            logger.warning(f"MCP configuration file not found at {self.config_path}")
            return
        try:
            from dotenv import dotenv_values
            env_file_vars = dotenv_values(".env")
            raw_text = self.config_path.read_text(encoding="utf-8")
            # Replace ${VAR_NAME} with .env value, settings attribute, or os.environ
            def replace_env(match):
                var_name = match.group(1)
                val = env_file_vars.get(var_name) or getattr(settings, var_name, None) or os.getenv(var_name, "")
                return str(val or "")

            resolved_text = re.sub(r"\$\{([A-Za-z0-9_]+)\}", replace_env, raw_text)
            data = json.loads(resolved_text)
            self.servers = data.get("mcpServers", {})
            logger.info(f"Loaded {len(self.servers)} MCP server configurations with env-substitution.")
        except Exception as e:
            logger.error(f"Failed to parse mcp_config.json: {e}")

    def _save_cache(self, cache_data: Dict[str, Any]):
        """Persist discovered tools to local cache for offline resilience."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write MCP tools cache: {e}")

    def _load_cache(self) -> Dict[str, Any]:
        """Load fallback tool definitions from disk cache if remote server is unreachable."""
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to read MCP tools cache: {e}")
        return {}

    async def discover_tools(self) -> List[Dict[str, Any]]:
        """Query all active servers via tools/list, cache their schemas, and provide offline fallback."""
        self.discovered_tools.clear()
        all_tools = []
        cached_all = self._load_cache()
        new_cache = {}

        for server_name, cfg in self.servers.items():
            if not cfg.get("enabled", True):
                continue

            tools = []
            try:
                tools = await self._query_tools_list(server_name, cfg)
                new_cache[server_name] = tools
            except Exception as e:
                logger.error(f"Failed discovering tools for server '{server_name}': {e}")
                # Fallback to cached tool definitions if live query fails
                if server_name in cached_all:
                    tools = cached_all[server_name]
                    new_cache[server_name] = tools
                    logger.warning(f"Using {len(tools)} cached tools for '{server_name}' due to connection issue.")

            for t in tools:
                full_name = f"mcp_{server_name}_{t['name']}"
                self.discovered_tools[full_name] = {
                    "server_name": server_name,
                    "tool_name": t["name"],
                    "original_tool": t,
                    "config": cfg
                }
                all_tools.append(mcp_to_openai_tool(server_name, t))

        if new_cache:
            self._save_cache(new_cache)

        logger.info(f"Discovered {len(self.discovered_tools)} total MCP tools across servers.")
        return all_tools

    def _parse_mcp_response(self, text: str) -> Dict[str, Any]:
        """Parse raw text or SSE stream formatted response into JSON dict."""
        text = text.strip()
        if text.startswith("{"):
            return json.loads(text)
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return json.loads(text)

    async def _query_tools_list(self, server_name: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query tools/list via HTTP/SSE endpoint or stdio subprocess."""
        url = cfg.get("url")
        if url:
            import httpx
            headers = dict(cfg.get("headers", {}))
            headers["Content-Type"] = "application/json"
            req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            async with httpx.AsyncClient(timeout=settings.TOOL_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, headers=headers, json=req)
                resp.raise_for_status()
                data = self._parse_mcp_response(resp.text)
                return data.get("result", {}).get("tools", [])

        # Fallback to stdio subprocess
        cmd = [cfg["command"]] + cfg.get("args", [])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(input=(json.dumps(req) + "\n").encode("utf-8")),
                timeout=settings.TOOL_TIMEOUT_SECONDS
            )
            resp = json.loads(stdout.decode("utf-8").strip())
            return resp.get("result", {}).get("tools", [])
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool via tools/call with human-friendly error translation and timeout protection."""
        if not self.discovered_tools:
            await self.discover_tools()

        if tool_name not in self.discovered_tools:
            return {"error": f"Tool '{tool_name}' is not registered."}

        info = self.discovered_tools[tool_name]
        server_name = info["server_name"]
        raw_name = info["tool_name"]
        cfg = info["config"]

        # 1. HTTP / SSE Transport
        url = cfg.get("url")
        if url:
            import httpx
            headers = dict(cfg.get("headers", {}))
            headers["Content-Type"] = "application/json"
            req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": raw_name,
                    "arguments": arguments
                }
            }
            try:
                async with httpx.AsyncClient(timeout=settings.TOOL_TIMEOUT_SECONDS) as client:
                    resp = await client.post(url, headers=headers, json=req)
                    resp.raise_for_status()
                    data = self._parse_mcp_response(resp.text)
                    res = data.get("result", {})
                    # If get_me returned login info, update authenticated_user
                    if "get_me" in raw_name and "login" in str(res):
                        for c in res.get("content", []):
                            txt = c.get("text", "")
                            m = re.search(r'"login":\s*"([^"]+)"', txt)
                            if m:
                                self.authenticated_user = m.group(1)
                                logger.info(f"Dynamically resolved authenticated GitHub user: {self.authenticated_user}")
                    return res
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code == 401:
                    msg = "Authentication failed (401 Unauthorized): Your GitHub Personal Access Token is invalid or expired. Please update GITHUB_PAT in your .env file."
                elif code == 403:
                    msg = "Access denied (403 Forbidden): Your GitHub Personal Access Token lacks required permissions or API rate limits were reached."
                elif code == 404:
                    msg = f"Resource not found (404 Not Found) on MCP endpoint for tool '{raw_name}'."
                else:
                    msg = f"Cloud MCP server returned HTTP error {code}: {e.response.text[:200]}"
                logger.error(f"HTTP MCP error on '{tool_name}': {msg}")
                return {"error": msg, "isError": True}
            except httpx.TimeoutException:
                msg = f"Cloud MCP tool execution timed out after {settings.TOOL_TIMEOUT_SECONDS}s."
                logger.error(msg)
                return {"error": msg, "isError": True}
            except Exception as e:
                logger.error(f"HTTP MCP tool '{tool_name}' unexpected error: {e}")
                return {"error": str(e), "isError": True}

        # 2. stdio Subprocess Transport
        cmd = [cfg["command"]] + cfg.get("args", [])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": raw_name,
                "arguments": arguments
            }
        }

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(input=(json.dumps(req) + "\n").encode("utf-8")),
                timeout=settings.TOOL_TIMEOUT_SECONDS
            )
            resp = json.loads(stdout.decode("utf-8").strip())
            return resp.get("result", {})
        except asyncio.TimeoutError:
            logger.error(f"MCP tool '{tool_name}' timed out after {settings.TOOL_TIMEOUT_SECONDS}s.")
            return {"error": f"Tool execution timed out ({settings.TOOL_TIMEOUT_SECONDS}s limit).", "isError": True}
        except Exception as e:
            logger.error(f"MCP tool '{tool_name}' error: {e}")
            return {"error": str(e), "isError": True}
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass

mcp_manager = MCPClientManager()
