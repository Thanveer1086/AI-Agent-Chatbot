"""Reference PostgreSQL Database MCP Server (stdio transport, newline-delimited JSON-RPC).

Read-only tools that report live data from the application database
(DATABASE_URL). No arbitrary SQL is accepted from the model.
"""
import sys
import os
import json
import asyncio

PROTOCOL_VERSION = "2025-06-18"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agent_chatbot")

TOOLS = [
    {
        "name": "query_master_data",
        "description": "Returns list of active business application domains and categories in the database.",
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {"include_categories": {"type": "boolean", "default": True}},
        },
    },
    {
        "name": "get_system_metrics",
        "description": "Returns counts of indexed knowledge documents and total vector chunks.",
        "annotations": {"readOnlyHint": True},
        "inputSchema": {"type": "object", "properties": {}},
    },
]


async def _fetch_master_data(include_categories: bool) -> dict:
    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL, timeout=10)
    try:
        apps = await conn.fetch("SELECT id, name, description FROM applications ORDER BY id;")
        data = {"applications": [dict(r) for r in apps]}
        if include_categories:
            cats = await conn.fetch("SELECT id, name, application_id FROM categories ORDER BY id;")
            data["categories"] = [dict(r) for r in cats]
        return data
    finally:
        await conn.close()


async def _fetch_metrics() -> dict:
    import asyncpg

    conn = await asyncpg.connect(DATABASE_URL, timeout=10)
    try:
        row = await conn.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM uploaded_files) AS total_documents,
                (SELECT count(*) FROM uploaded_files WHERE is_enabled) AS enabled_documents,
                (SELECT count(*) FROM primary_vector_chunks) AS total_chunks,
                (SELECT count(*) FROM approved_answers) AS approved_answers,
                (SELECT count(*) FROM chat_sessions) AS chat_sessions,
                current_setting('server_version') AS server_version;
            """
        )
        metrics = dict(row)
        metrics["vector_dimension"] = 1536
        metrics["database_engine"] = f"PostgreSQL {metrics.pop('server_version')} (pgvector)"
        return metrics
    finally:
        await conn.close()


def _text_result(req_id, text, is_error=False):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
    }


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
                "serverInfo": {"name": "internal_database", "version": "1.1.0"},
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
        try:
            if name == "query_master_data":
                data = asyncio.run(_fetch_master_data(bool(args.get("include_categories", True))))
                return _text_result(req_id, json.dumps(data, default=str))
            if name == "get_system_metrics":
                return _text_result(req_id, json.dumps(asyncio.run(_fetch_metrics()), default=str))
        except Exception as e:
            return _text_result(req_id, f"Database query failed: {e}", is_error=True)
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
            if "id" not in req:
                continue
            resp = handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Error processing MCP request: {e}\n")


if __name__ == "__main__":
    main()
