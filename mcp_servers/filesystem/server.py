"""Reference Filesystem MCP Server (stdio transport, newline-delimited JSON-RPC).

Only exposes files inside ./storage/staging. Every path supplied by the model is
resolved and checked so it cannot escape that directory (e.g. "../../.env").
"""
import sys
import json
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
STAGING_DIR = Path("./storage/staging")
MAX_LINES_LIMIT = 500


def _text_result(req_id, text, is_error=False):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
    }


def _resolve_staged(relative: str) -> Path:
    """Resolve a path inside the staging directory or raise ValueError."""
    base = STAGING_DIR.resolve()
    target = (base / relative).resolve()
    if target != base and base not in target.parents:
        raise ValueError("Access outside the staging directory is not allowed.")
    return target


TOOLS = [
    {
        "name": "list_staging_files",
        "description": "Lists all staged knowledge files waiting for or completed in processing.",
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {"subpath": {"type": "string", "default": ""}},
        },
    },
    {
        "name": "read_staged_file",
        "description": "Reads lines from a staged text or log file.",
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "The exact name of the file"},
                "max_lines": {"type": "integer", "default": 50},
            },
            "required": ["filename"],
        },
    },
]


def handle_request(req):
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": req.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "local_filesystem", "version": "1.1.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        STAGING_DIR.mkdir(parents=True, exist_ok=True)

        if name == "list_staging_files":
            try:
                folder = _resolve_staged(str(args.get("subpath", "") or ""))
            except ValueError as e:
                return _text_result(req_id, str(e), is_error=True)
            if not folder.is_dir():
                return _text_result(req_id, "Folder not found.", is_error=True)
            files = sorted(f.name for f in folder.iterdir() if f.is_file())
            return _text_result(req_id, f"Staged files: {', '.join(files) if files else 'None'}")

        if name == "read_staged_file":
            filename = str(args.get("filename", "") or "")
            try:
                target = _resolve_staged(filename)
            except ValueError as e:
                return _text_result(req_id, str(e), is_error=True)
            if not filename or not target.is_file():
                return _text_result(req_id, f"File '{filename}' not found.", is_error=True)
            try:
                max_lines = int(args.get("max_lines", 50))
            except (TypeError, ValueError):
                max_lines = 50
            max_lines = max(1, min(max_lines, MAX_LINES_LIMIT))
            lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()[:max_lines]
            return _text_result(req_id, "\n".join(lines))

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": f"Unknown tool: {name}"},
        }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            # Notifications (no id) never get a response.
            if "id" not in req:
                continue
            resp = handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error processing MCP request: {e}\n")


if __name__ == "__main__":
    main()
