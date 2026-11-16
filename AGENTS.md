# AGENTS.md — Autonomous Agentic ChatBot

This file provides system context, architectural guidelines, and development rules for AI coding agents (such as Antigravity, Gemini, Codex, and Claude) working on this repository.

---

## 1. Project Overview & Tech Stack

This repository is a production-grade **Autonomous Agentic AI System** with real-time tool calling and enterprise hybrid RAG.

- **Agent Orchestrator**: LangGraph (`StateGraph` with Plan $\rightarrow$ Execute $\rightarrow$ Reflect $\rightarrow$ Synthesize loop)
- **Backend**: Python 3.11 + FastAPI + Uvicorn (Port 8000)
- **Frontend**: Vite + React 18 + TailwindCSS + Lucide Icons (Port 3000)
- **Database**: PostgreSQL 16 + `pgvector` HNSW index (Port 5432)
- **Database Web GUI**: Adminer (Port 8080)
- **Tool Protocol**: Model Context Protocol (MCP) supporting local `stdio` subprocesses and cloud `HTTP/SSE`
- **Embeddings**: Google `gemini-embedding-2` (3072 sliced and L2-normalized to 1536 dimensions)

---

## 2. Directory Layout

```text
AI-Agent-ChatBot/
├── backend/
│   ├── src/
│   │   ├── api/             # FastAPI routers (chat stream, file uploads, MCP inspection)
│   │   ├── core/
│   │   │   ├── agent/       # LangGraph workflow, planner, tool executor, reflection nodes
│   │   │   ├── db/          # PostgreSQL database session & connection pooling
│   │   │   ├── mcp/         # MCP Client Manager, JSON-RPC, HTTP/SSE & stdio handlers
│   │   │   ├── rag/         # Embeddings, chunking, XML docx/pdf ingestion, hybrid search
│   │   │   └── security/    # JWT authentication & DEV_AUTH_BYPASS
│   │   └── config.py        # Pydantic Settings
├── frontend/                # Vite React user interface
├── mcp_servers/             # Local bundled MCP tool servers (database, filesystem)
├── mcp_config.json          # Tool catalog definition (stdio & remote HTTP/SSE)
├── docker-compose.yml       # Orchestrates frontend, backend, db, and adminer
├── .env                     # Local environment secrets (IGNORED BY GIT)
├── .env.example             # Configuration template
└── README.md                # User-facing project documentation
```

---

## 3. Core Architectural Rules

1. **Dual MCP Support**:
   - Local tools use `stdio` transport (`command` + `args`).
   - Remote tools (e.g. GitHub Copilot MCP) use `HTTP/SSE` transport (`url` + `headers`).
   - The planner must pass explicit parameters matching the tool's JSON schema (e.g. `query` parameter for `search_repositories`).

2. **Vector Dimension Alignment**:
   - The PostgreSQL vector column is defined as `vector(1536)`.
   - `gemini-embedding-2` produces 3072 dimensions. Always slice to `[:1536]` and normalize with unit L2 norm (`v / norm(v)`) before storage or cosine querying.

3. **Hybrid RAG Pipeline**:
   - Combines vector similarity (`<=>` cosine distance) with PostgreSQL `tsvector` full-text search.
   - Merged using Reciprocal Rank Fusion (RRF) with source citation tracking.

4. **Security & Secrets**:
   - NEVER commit `.env`, API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`), or GitHub Personal Access Tokens.
   - Keep `.env` strictly in `.gitignore`.

---

## 4. Development & Docker Workflow

| Action | Command |
| :--- | :--- |
| **Start full stack** | `docker compose up -d` |
| **Restart backend (after .env edit)** | `docker compose up -d backend` |
| **Restart backend (clean reboot)** | `docker compose restart backend` |
| **View backend live logs** | `docker compose logs -f backend` |
| **Rebuild after adding python packages** | `docker compose up -d --build backend` |
| **Check running containers** | `docker compose ps` |
| **Stop stack** | `docker compose down` |

---

## 5. Verification Checkpoints

When making modifications, verify functionality across these endpoints:

1. **MCP Catalog Discovery**:
   ```bash
   GET http://localhost:8000/api/mcp/tools
   ```
   Should list available tools across all configured MCP servers.

2. **Frontend UI**:
   - Open `http://localhost:3000`
   - Test Agent Chat with live reasoning steps and tool execution latency badges.
   - Test Knowledge Studio for document uploads and indexing.

3. **Database Inspection**:
   - Open `http://localhost:8080` (System: PostgreSQL, Server: `db`, User/Pass: `postgres`/`postgres`, DB: `agent_chatbot`).
