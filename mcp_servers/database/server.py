"""Reference PostgreSQL Database MCP Server (stdio transport)."""
import sys
import json

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
                        "name": "query_master_data",
                        "description": "Returns list of active business application domains and categories in the database.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "include_categories": {"type": "boolean", "default": True}
                            }
                        }
                    },
                    {
                        "name": "get_system_metrics",
                        "description": "Returns counts of indexed knowledge documents and total vector chunks.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")

        if name == "query_master_data":
            data = {
                "applications": [
                    {"id": 1, "name": "General Knowledge", "status": "Active"},
                    {"id": 2, "name": "Customer Support", "status": "Active"}
                ]
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data)}],
                    "isError": False
                }
            }

        elif name == "get_system_metrics":
            metrics = {
                "total_documents": 5,
                "total_chunks": 42,
                "vector_dimension": 1536,
                "database_engine": "PostgreSQL 15 (pgvector + pg_trgm)"
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(metrics)}],
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
