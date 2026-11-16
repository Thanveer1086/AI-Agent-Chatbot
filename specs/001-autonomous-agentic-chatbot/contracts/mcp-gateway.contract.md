# Interface Contract: Model Context Protocol (MCP) Gateway

**Component**: `backend/src/core/mcp/`  
**Protocol Version**: Model Context Protocol (JSON-RPC 2.0)  

---

## 1. Server Configuration Format (`mcp_config.json`)

Stored in the backend root or configured via environment variables:

```json
{
  "mcpServers": {
    "local_filesystem": {
      "transport": "stdio",
      "command": "python",
      "args": ["-m", "mcp_servers.filesystem"],
      "env": {
        "ALLOWED_ROOT": "./storage/staging"
      },
      "enabled": true
    },
    "internal_database": {
      "transport": "stdio",
      "command": "python",
      "args": ["-m", "mcp_servers.database"],
      "env": {
        "DB_URL": "${DATABASE_URL}"
      },
      "enabled": true
    },
    "remote_jira_service": {
      "transport": "sse",
      "url": "https://mcp-jira.internal.company.com/sse",
      "headers": {
        "Authorization": "Bearer ${JIRA_MCP_SECRET}"
      },
      "enabled": false
    }
  }
}
```

---

## 2. Dynamic Tool Discovery Contract (`tools/list`)

At startup and on demand, the `MCPClientManager` executes the standard MCP discovery command:

### Client Request (JSON-RPC 2.0)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

### Server Response
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "read_staged_file",
        "description": "Reads raw content from an uploaded file in the staging directory.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "filename": { "type": "string", "description": "The exact name of the file to inspect" },
            "max_lines": { "type": "integer", "default": 100 }
          },
          "required": ["filename"]
        }
      }
    ]
  }
}
```

---

## 3. Tool Invocation Contract (`tools/call`)

### Execution Request
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "read_staged_file",
    "arguments": {
      "filename": "server_logs.txt",
      "max_lines": 50
    }
  }
}
```

### Execution Response
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[2026-11-12 10:00:00] INFO Server started successfully.\n[2026-11-12 10:01:23] WARN Database connection latency spiked."
      }
    ],
    "isError": false
  }
}
```

---

## 4. MCP Management API Endpoints

- `GET /api/mcp/servers`: Returns list of configured servers and live connection status (`online`, `offline`, `degraded`).
- `GET /api/mcp/tools`: Returns catalogue of all dynamically loaded tools and their input schemas.
- `POST /api/mcp/reload`: Triggers runtime re-discovery across all active MCP servers without restarting FastAPI.
