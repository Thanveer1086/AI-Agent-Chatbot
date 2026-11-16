"""Reference Filesystem MCP Server (stdio transport)."""
import sys
import json
import os
from pathlib import Path

def handle_request(req):
    method = req.get("method")
    req_id = req.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "list_staging_files",
                        "description": "Lists all staged knowledge files waiting for or completed in processing.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "subpath": {"type": "string", "default": ""}
                            }
                        }
                    },
                    {
                        "name": "read_staged_file",
                        "description": "Reads lines from a staged text or log file.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string", "description": "The exact name of the file"},
                                "max_lines": {"type": "integer", "default": 50}
                            },
                            "required": ["filename"]
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        staging_dir = Path("./storage/staging")
        staging_dir.mkdir(parents=True, exist_ok=True)

        if name == "list_staging_files":
            files = [f.name for f in staging_dir.iterdir() if f.is_file()]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Staged files: {', '.join(files) if files else 'None'}"}],
                    "isError": False
                }
            }

        elif name == "read_staged_file":
            target = staging_dir / args.get("filename", "")
            if not target.exists():
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"File '{args.get('filename')}' not found."}],
                        "isError": True
                    }
                }
            lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()[:args.get("max_lines", 50)]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": "\n".join(lines)}],
                    "isError": False
                }
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not found"}
    }

def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error processing MCP request: {e}\n")

if __name__ == "__main__":
    main()
