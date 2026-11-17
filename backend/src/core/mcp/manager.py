"""Model Context Protocol (MCP) Client Manager.

Implements the MCP client side of the lifecycle for both transports:
- stdio: one long-lived subprocess per server, `initialize` handshake once, then
  newline-delimited JSON-RPC requests serialised through a lock.
- Streamable HTTP: `initialize` handshake, `Mcp-Session-Id` reuse, JSON or SSE
  responses. Falls back to stateless requests if a server rejects the handshake.
"""
import json
import re
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from src.core.mcp.adapters import mcp_to_openai_tool
from src.config import settings

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "ai-agent-chatbot", "version": "0.2.0"}
STDIO_LINE_LIMIT = 16 * 1024 * 1024


class MCPError(RuntimeError):
    """A JSON-RPC error or transport failure talking to an MCP server."""


def _init_params() -> Dict[str, Any]:
    return {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO}


class StdioSession:
    """A persistent stdio MCP server process."""

    def __init__(self, name: str, cfg: Dict[str, Any]):
        self.name = name
        self.cfg = cfg
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._next_id = 0
        self._stderr_task: Optional[asyncio.Task] = None

    async def _drain_stderr(self):
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            logger.debug(f"[mcp:{self.name}] {line.decode('utf-8', 'replace').rstrip()}")

    async def _start(self):
        cmd = [self.cfg["command"]] + list(self.cfg.get("args", []))
        env = {**os.environ, **{k: str(v) for k, v in (self.cfg.get("env") or {}).items()}}
        self.proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=STDIO_LINE_LIMIT,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self._send_and_wait("initialize", _init_params(), settings.TOOL_TIMEOUT_SECONDS)
        await self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
        logger.info(f"MCP stdio server '{self.name}' started and initialized.")

    async def _write(self, payload: Dict[str, Any]):
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    async def _send_and_wait(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        self._next_id += 1
        req_id = self._next_id
        await self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        async def read_response():
            assert self.proc and self.proc.stdout
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    raise MCPError(f"MCP server '{self.name}' closed its output.")
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue  # stray log output
                if msg.get("id") == req_id:
                    return msg

        msg = await asyncio.wait_for(read_response(), timeout=timeout)
        if "error" in msg:
            err = msg["error"]
            raise MCPError(f"{err.get('message', 'MCP error')} (code {err.get('code')})")
        return msg.get("result", {})

    async def request(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        async with self._lock:
            if self.proc is None or self.proc.returncode is not None:
                await self._start()
            try:
                return await self._send_and_wait(method, params, timeout)
            except (asyncio.TimeoutError, MCPError, OSError) as e:
                # A timed-out or broken server is restarted on the next request.
                if not isinstance(e, MCPError) or "closed" in str(e):
                    await self._kill()
                raise

    async def _kill(self):
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
                await self.proc.wait()
            except Exception:
                pass
        if self._stderr_task:
            self._stderr_task.cancel()
        self.proc = None

    async def close(self):
        async with self._lock:
            await self._kill()


class MCPClientManager:
    def __init__(self, config_path: str = "mcp_config.json", cache_path: str = "storage/mcp_tools_cache.json"):
        self.config_path = Path(config_path)
        self.cache_path = Path(cache_path)
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.discovered_tools: Dict[str, Dict[str, Any]] = {}
        self.authenticated_user: Optional[str] = settings.GITHUB_USERNAME or None
        self._stdio: Dict[str, StdioSession] = {}
        self._http_sessions: Dict[str, Optional[str]] = {}
        self._http_lock = asyncio.Lock()
        self._discovery_lock = asyncio.Lock()
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

            def replace_env(match):
                var_name = match.group(1)
                val = env_file_vars.get(var_name) or getattr(settings, var_name, None) or os.getenv(var_name, "")
                # JSON-escape so a value with quotes/backslashes cannot break the config
                return json.dumps(str(val or ""))[1:-1]

            resolved_text = re.sub(r"\$\{([A-Za-z0-9_]+)\}", replace_env, raw_text)
            data = json.loads(resolved_text)
            self.servers = data.get("mcpServers", {})
            logger.info(f"Loaded {len(self.servers)} MCP server configurations with env-substitution.")
        except Exception as e:
            logger.error(f"Failed to parse mcp_config.json: {e}")

    # ------------------------------------------------------------------ cache
    def _save_cache(self, cache_data: Dict[str, Any]):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write MCP tools cache: {e}")

    def _load_cache(self) -> Dict[str, Any]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to read MCP tools cache: {e}")
        return {}

    # ------------------------------------------------------------- transport
    @staticmethod
    def _parse_mcp_response(text: str, req_id: Optional[int] = None) -> Dict[str, Any]:
        """Parse a JSON body or an SSE stream and return the message answering `req_id`."""
        text = text.strip()
        if text.startswith("{"):
            return json.loads(text)

        messages: List[Dict[str, Any]] = []
        data_lines: List[str] = []
        for line in text.splitlines() + [""]:
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif not line.strip() and data_lines:
                try:
                    messages.append(json.loads("\n".join(data_lines)))
                except json.JSONDecodeError:
                    pass
                data_lines = []
        for msg in messages:
            if req_id is None or msg.get("id") == req_id:
                return msg
        if messages:
            return messages[-1]
        raise MCPError("Empty or unparseable MCP response")

    async def _http_post(
        self, cfg: Dict[str, Any], payload: Dict[str, Any], session_id: Optional[str]
    ) -> Tuple[Optional[Dict[str, Any]], Any]:
        import httpx
        headers = dict(cfg.get("headers", {}))
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/event-stream"
        headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        async with httpx.AsyncClient(timeout=settings.TOOL_TIMEOUT_SECONDS) as client:
            resp = await client.post(cfg["url"], headers=headers, json=payload)
            resp.raise_for_status()
            if "id" not in payload or not resp.text.strip():
                return None, resp.headers
            return self._parse_mcp_response(resp.text, payload["id"]), resp.headers

    async def _ensure_http_session(self, server_name: str, cfg: Dict[str, Any]) -> Optional[str]:
        async with self._http_lock:
            if server_name in self._http_sessions:
                return self._http_sessions[server_name]
            session_id: Optional[str] = None
            try:
                msg, headers = await self._http_post(
                    cfg, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": _init_params()}, None
                )
                if msg and "error" in msg:
                    raise MCPError(msg["error"].get("message", "initialize failed"))
                session_id = headers.get("mcp-session-id")
                await self._http_post(cfg, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
                logger.info(f"MCP HTTP server '{server_name}' initialized (session={'yes' if session_id else 'stateless'}).")
            except Exception as e:
                logger.warning(f"MCP initialize failed for '{server_name}' ({e}); continuing stateless.")
            self._http_sessions[server_name] = session_id
            return session_id

    async def _request(self, server_name: str, cfg: Dict[str, Any], method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send one JSON-RPC request over the server's transport and return `result`."""
        if cfg.get("url"):
            import httpx
            for attempt in range(2):
                session_id = await self._ensure_http_session(server_name, cfg)
                try:
                    msg, _ = await self._http_post(
                        cfg, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, session_id
                    )
                except httpx.HTTPStatusError as e:
                    # 404 with a session id means the server expired it: re-initialize once.
                    if e.response.status_code == 404 and session_id and attempt == 0:
                        self._http_sessions.pop(server_name, None)
                        continue
                    raise
                if not msg:
                    raise MCPError("Empty MCP response")
                if "error" in msg:
                    err = msg["error"]
                    raise MCPError(f"{err.get('message', 'MCP error')} (code {err.get('code')})")
                return msg.get("result", {})
            raise MCPError("MCP session could not be re-established")

        if "command" not in cfg:
            raise MCPError(f"MCP server '{server_name}' has neither 'url' nor 'command' configured")
        session = self._stdio.get(server_name)
        if session is None:
            session = self._stdio[server_name] = StdioSession(server_name, cfg)
        return await session.request(method, params, settings.TOOL_TIMEOUT_SECONDS)

    # ------------------------------------------------------------- discovery
    async def _query_tools_list(self, server_name: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        for _ in range(20):  # pagination guard
            params = {"cursor": cursor} if cursor else {}
            result = await self._request(server_name, cfg, "tools/list", params)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def discover_tools(self) -> List[Dict[str, Any]]:
        """Query all active servers via tools/list (concurrently), with an offline cache fallback."""
        async with self._discovery_lock:
            cached_all = self._load_cache()
            active = {n: c for n, c in self.servers.items() if c.get("enabled", True)}

            async def discover(name: str, cfg: Dict[str, Any]):
                try:
                    return name, await self._query_tools_list(name, cfg), None
                except Exception as e:
                    return name, None, e

            results = await asyncio.gather(*(discover(n, c) for n, c in active.items()))

            discovered: Dict[str, Dict[str, Any]] = {}
            all_tools: List[Dict[str, Any]] = []
            new_cache: Dict[str, Any] = {}
            for server_name, tools, error in results:
                if error is not None:
                    logger.error(f"Failed discovering tools for server '{server_name}': {error}")
                    tools = cached_all.get(server_name)
                    if tools is None:
                        continue
                    logger.warning(f"Using {len(tools)} cached tools for '{server_name}' due to connection issue.")
                new_cache[server_name] = tools
                cfg = active[server_name]
                for t in tools:
                    full_name = f"mcp_{server_name}_{t['name']}"
                    discovered[full_name] = {
                        "server_name": server_name,
                        "tool_name": t["name"],
                        "original_tool": t,
                        "config": cfg,
                    }
                    all_tools.append(mcp_to_openai_tool(server_name, t))

            # Swap in one step so concurrent readers never see a half-built catalog
            self.discovered_tools = discovered
            if new_cache:
                self._save_cache(new_cache)

            logger.info(f"Discovered {len(discovered)} total MCP tools across servers.")
            return all_tools

    # ------------------------------------------------------------- execution
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool via tools/call with human-friendly error translation and timeout protection."""
        import httpx

        if not self.discovered_tools:
            await self.discover_tools()

        info = self.discovered_tools.get(tool_name)
        if info is None:
            return {"error": f"Tool '{tool_name}' is not registered.", "isError": True}

        server_name, raw_name, cfg = info["server_name"], info["tool_name"], info["config"]
        try:
            res = await self._request(server_name, cfg, "tools/call", {"name": raw_name, "arguments": arguments})
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 401:
                msg = "Authentication failed (401 Unauthorized): the MCP server rejected the credentials. Check the token in your .env file."
            elif code == 403:
                msg = "Access denied (403 Forbidden): the token lacks the required permissions or a rate limit was reached."
            elif code == 404:
                msg = f"Resource not found (404 Not Found) on MCP endpoint for tool '{raw_name}'."
            else:
                msg = f"MCP server returned HTTP error {code}: {e.response.text[:200]}"
            logger.error(f"HTTP MCP error on '{tool_name}': {msg}")
            return {"error": msg, "isError": True}
        except (httpx.TimeoutException, asyncio.TimeoutError):
            msg = f"MCP tool execution timed out after {settings.TOOL_TIMEOUT_SECONDS}s."
            logger.error(f"{tool_name}: {msg}")
            return {"error": msg, "isError": True}
        except Exception as e:
            logger.error(f"MCP tool '{tool_name}' error: {e}")
            return {"error": str(e), "isError": True}

        # Remember the GitHub login so repository searches can default to the user's repos
        if raw_name == "get_me":
            for c in res.get("content", []) or []:
                m = re.search(r'"login":\s*"([^"]+)"', c.get("text", "") if isinstance(c, dict) else "")
                if m:
                    self.authenticated_user = m.group(1)
                    logger.info(f"Resolved authenticated GitHub user: {self.authenticated_user}")
        return res

    async def close(self):
        """Stop all stdio server processes."""
        await asyncio.gather(*(s.close() for s in self._stdio.values()), return_exceptions=True)
        self._stdio.clear()
        self._http_sessions.clear()


mcp_manager = MCPClientManager()
