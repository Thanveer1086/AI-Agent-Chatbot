# Quickstart Validation Guide: Autonomous Agentic Chatbot

**Feature**: `001-autonomous-agentic-chatbot`  
**Date**: 2026-11-12  
**Status**: Ready for Validation  

This guide provides step-by-step instructions to spin up the full-stack system and execute end-to-end verification scenarios proving the feature works as specified.

---

## 1. Prerequisites

- **Docker & Docker Compose** (v24.0+)
- **Python 3.11+** (for host development)
- **Node.js 18+ & npm/pnpm** (for frontend development)
- **API Keys**: OpenAI API key (`OPENAI_API_KEY`) or Google Gemini API key (`GEMINI_API_KEY`)

---

## 2. Environment Setup

Copy `.env.example` to `.env` in the repository root:

```bash
# Core Environment Settings
API_USED=openai
OPENAI_API_KEY=sk-proj-...
# or GEMINI_API_KEY=AIzaSy...

# Database & Storage
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agent_chatbot
AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true
DEV_STORAGE_LOCAL_PATH=./storage/blobs

# Security & Mode
DEV_AUTH_BYPASS=true
JWT_SECRET=super-secret-key-change-in-prod
```

---

## 3. Starting the Stack

### Option A: 1-Click Launch with Docker Compose (Recommended)
```bash
docker compose up -d --build
```
This boots:
1. **PostgreSQL 15** with `pgvector` & `pg_trgm` on `localhost:5432`
2. **FastAPI Backend** with MCP & LangGraph on `http://localhost:8000`
3. **Vite React Frontend** on `http://localhost:3000`

### Option B: Standalone Native Development
```bash
# Terminal 1: Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -e .
uvicorn src.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
```

---

## 4. End-to-End Validation Scenarios

### Scenario 1: Health & MCP Tool Discovery Verification
Verify the backend started and automatically discovered the bundled MCP tools:
```bash
curl http://localhost:8000/api/mcp/tools
```
**Expected Outcome**: Returns HTTP 200 with JSON listing discovered tools:
- `read_staged_file` (from `local_filesystem` MCP)
- `execute_readonly_query` (from `internal_database` MCP)

---

### Scenario 2: Ingest Sample Knowledge Document
Upload a sample markdown document to index knowledge chunks:
```bash
curl -X POST http://localhost:8000/api/upload_file \
  -F "file=@tests/fixtures/sample_policy.md" \
  -F "application_ids=[1]" \
  -F "document_type_id=1"
```
**Expected Outcome**: Returns HTTP 200 with `success: true` and `indexed_chunks > 0`. Chunks are verified in `primary_vector_chunks` with 1536-dim vector embeddings.

---

### Scenario 3: Real-Time Streaming Agent Chat (SSE)
Test the agent's autonomous planning, multi-tool execution, and streaming response:
```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"application_id": 1, "message": "What does our sample policy say about travel?"}'
```
**Expected Outcome**: The terminal streams SSE events in order:
1. `event: thought_step` (Agent plans to search knowledge base)
2. `event: tool_start` (Calling `knowledge_base_search`)
3. `event: tool_result` (Retrieved matching policy chunks)
4. `event: token` (Incremental text words streaming)
5. `event: citation` (References `sample_policy.md` with relevance score)
6. `event: done` (Closing stream with session and message ID)

---

### Scenario 4: Frontend UI Interactive Verification
1. Open your browser at `http://localhost:3000`.
2. Submit a question in the chat input.
3. Observe:
   - Real-time token streaming.
   - An expandable **Thought Trace** accordion showing tools called and latencies.
   - Clickable **Citation Badges** opening the document preview drawer.
4. Switch to the **Knowledge Admin Studio** tab:
   - Drag and drop a document to upload and index it.
   - Toggle the document status switch from `Enabled` to `Disabled`.
   - Verify that disabled documents are instantly excluded from future chat answers.
