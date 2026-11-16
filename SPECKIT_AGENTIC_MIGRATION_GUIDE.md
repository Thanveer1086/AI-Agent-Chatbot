# Spec-Kit Framework & Greenfield Build Blueprint
## Building an Autonomous Agentic Chatbot with MCP, Multi-Tool Calling, Advanced RAG, and Modern UI

**Project:** AI-Agent-ChatBot (Greenfield Build from Scratch)  
**Date:** November 2026  
**Status:** Full-Stack Architecture Review & Planning  

---

## 1. System Evaluation: Backend & Frontend Scope

| Dimension | Previous Technical Spec (Trinity API) | New Target System (Greenfield Build) |
| :--- | :--- | :--- |
| **System Scope** | Backend API only (FastAPI) | **Full-Stack** (FastAPI Backend + React/Next.js Frontend) |
| **System Classification**| Advanced / Hybrid RAG Pipeline | Autonomous Multi-Tool Orchestrator Agent |
| **User Interface (UI)** | None (Swagger / Postman only) | **Modern Chat UI & Knowledge Admin Studio** |
| **Tool Calling** | None (Single fixed pipeline) | Multi-tool calling (Parallel & Sequential) |
| **External Integrations**| PostgreSQL, Azure Blob, OpenAI/Gemini | **Model Context Protocol (MCP)** Client Gateway |
| **Knowledge Base** | The entire system flow | Refactored into a callable Tool (`knowledge_search`) |
| **Decision Engine** | Prompt-based classifier in ticket chat | Orchestrator Agent with state & tool reasoning |

---

## 2. Complete Technology Stack Matrix

### A. Frontend Layer (User Interface)
* **Framework:** **Next.js (App Router, React, TypeScript)** or **Vite + React (TypeScript)**
* **Styling & Design System:** **Tailwind CSS** + **shadcn/ui** (Radix UI primitives)
* **Icons & Visuals:** **Lucide React**
* **Streaming & Real-time:** **Server-Sent Events (SSE)** via `fetch` streaming reader
* **Markdown & Code Rendering:** `react-markdown`, `remark-gfm`, `rehype-highlight` (for syntax highlighting)
* **State Management:** **Zustand** (for chat sessions, active tools, agent state)

### B. Backend & Agent Layer
* **API Framework:** **FastAPI** (Python 3.11+, Pydantic v2, asyncpg)
* **Agent Orchestrator:** **LangGraph** (Stateful ReAct / Plan-and-Execute Graph with checkpointing)
* **Tool Protocol:** **Model Context Protocol (MCP)** using the official Python `mcp` SDK
* **LLM Engine:** **OpenAI (`gpt-4o` / `o3-mini`)** & **Google Gemini (2.0 Flash / Pro)**
* **Embedding Model:** OpenAI / Gemini embeddings (dimension: 1536)

### C. Knowledge & Storage Layer
* **Vector & Metadata DB:** **PostgreSQL** with `pgvector` (HNSW cosine similarity) & `pg_trgm` (BM25 keyword search)
* **Reranking:** **CrossEncoder** (`sentence-transformers/ms-marco-MiniLM-L-6-v2`)
* **Document Parsing:** **Docling** (converting PDF, DOCX, DOC to Markdown) + Tabular chunkers (CSV, Excel)
* **Media Transcription:** **FFmpeg** + Speech-to-Text API
* **Object / Blob Storage:** **Azure Blob Storage** (raw documents, transcripts, and media)

---

## 3. Frontend UI Specifications & Core Views

The application will feature two interconnected UI workspaces:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AI AGENT CHATBOT UI                             │
├───────────────────────────────┬────────────────────────────────────────┤
│  WORKSPACE 1: ADMIN & KNOWLEDGE│  WORKSPACE 2: AGENTIC CHAT             │
│                               │                                        │
│  📁 Knowledge Ingestion:      │  User: "Check ticket #402 & find docs" │
│  - Drag & Drop Upload         │                                        │
│  - Application / Category     │  🤖 Agent:                             │
│  - File Table (Toggle, Chunks)│  ┌─ Thought Trace (Accordion) ───────┐ │
│                               │  │ ⚡ Calling MCP: Ticket #402       │ │
│  ⚙️ Admin Studio:             │  │ 🔍 Knowledge Base: "Auth 502"     │ │
│  - Draft & Override Answers   │  │ 🎯 Reranked 20 Chunks             │ │
│  - Feedback Analytics         │  └───────────────────────────────────┘ │
│                               │                                        │
│  🔌 MCP Tool Monitor:         │  "Here is the issue and resolution..." │
│  - Active MCP Servers         │  [Source: auth_guide.pdf (94% Match)]  │
│  - Tool Schemas & Status      │  [Thumbs Up / Thumbs Down Feedback]   │
└───────────────────────────────┴────────────────────────────────────────┘
```

### View 1: Agentic Chat Workspace
1. **Real-time Streaming Chat:** Token-by-token generation with markdown and code formatting.
2. **Expandable Agent Thought / Tool Trace:** Visual badges showing what the agent is currently thinking and executing (e.g., *"Calling Jira MCP"*, *"Searching Knowledge Base"*).
3. **Interactive Citations Drawer:** Clickable badges linking directly to referenced documents with similarity scores.
4. **Session & History Sidebar:** Multi-session history, application switching, and conversation clearing.

### View 2: Knowledge & Admin Studio
1. **Document Ingestion Hub:** Drag-and-drop file upload supporting `.pdf`, `.docx`, `.csv`, `.xlsx`, `.txt`, `.md`, and `.mp4`.
2. **Document Management Grid:** View uploaded files, chunk counts, enable/disable toggle switches, delete, and download original files.
3. **Q&A Override & Review:** Review flagged questions, draft answers, publish verified overrides, and inspect user feedback ratings.
4. **MCP Connection Inspector:** View connected MCP servers, tool names, schemas, and live latency.

---

## 4. Full-Stack End-to-End Architecture

```
  +-------------------------------------------------------------------+
  |                  FRONTEND (Next.js / React + Tailwind)            |
  |  - Agent Chat Interface (SSE Streaming, Thought Trace, Citations) |
  |  - Knowledge Admin Studio (Drag & Drop Ingestion, File Controls)  |
  +---------------------------------+---------------------------------+
                                    | HTTP / SSE (EventStream)
                                    v
  +-------------------------------------------------------------------+
  |                  BACKEND API GATEWAY (FastAPI)                    |
  |  - Auth & Guardrails (/api/auth, /api/guardrails)                 |
  |  - Chat & Streaming Routes (/api/chat/stream, /api/applications)  |
  |  - Ingestion & File Routes (/api/upload, /api/files)              |
  +---------------------------------+---------------------------------+
                                    |
                                    v
  +-------------------------------------------------------------------+
  |                 ORCHESTRATOR AGENT (LangGraph Engine)             |
  |  - ReAct / Plan-and-Execute Loop                                  |
  |  - Multi-Tool Execution Engine (Parallel & Sequential)            |
  |  - Reflection & Self-Evaluation Step                              |
  +-----------------+-------------------------------+-----------------+
                    |                               |
                    v                               v
  +----------------------------------+ +------------------------------+
  |       RAG AS A TOOL              | |      MCP CLIENT GATEWAY      |
  |   (`knowledge_base_search`)      | |  (Model Context Protocol)    |
  +----------------------------------+ +------------------------------+
  | - Hybrid Search (pgvector + BM25)| | - stdio & SSE Transports     |
  | - Reciprocal Rank Fusion (RRF)   | | - Dynamic Tool Discovery     |
  | - CrossEncoder Reranking         | | - External Systems (Jira,    |
  | - Multi-Application Filtering    | |   GitHub, SQL, Internal APIs)|
  +-----------------+----------------+ +--------------+---------------+
                    |                               |
                    +---------------+---------------+
                                    |
                                    v
  +-------------------------------------------------------------------+
  |                         DATA & STORAGE LAYER                      |
  |  - PostgreSQL: Master Data, History, pgvector Chunks, pg_trgm BM25|
  |  - Azure Blob Storage: Raw files, transcripts, media assets       |
  +-------------------------------------------------------------------+
```

---

## 5. Ready-to-Run Spec-Kit Commands & Prompts

Copy and run these commands step-by-step in your Antigravity chat:

### Step 1: Constitution
```text
/speckit.constitution Create the constitution for our project: Build a greenfield, full-stack Autonomous Agentic Chatbot with MCP tools, Advanced RAG, and a modern React/Next.js UI.

Core Invariants:
1. Full-Stack Separation: Clean boundary between the Next.js/React frontend and the FastAPI backend.
2. Architecture Modularity: Clear isolation between Agent Orchestrator, MCP Gateway, RAG Tool, and Database layers.
3. Python Async Standards: asyncpg for PostgreSQL, httpx for networking, asyncio.gather for parallel tool calls.
4. Frontend UX Standards: TypeScript, Tailwind CSS, shadcn/ui, real-time SSE streaming, and expandable agent thought traces.
5. Strict Type Safety: Pydantic v2 on backend; TypeScript interfaces matching API schemas on frontend.
6. Zero hardcoded secrets; strict validation and isolation for external MCP tools.
```

### Step 2: Specification
```text
/speckit.specify Define the full technical and functional specification for our Full-Stack Autonomous Agentic Chatbot:

Key Requirements:
1. Frontend Specification (Next.js/React + Tailwind + shadcn/ui):
   - Streaming Chat UI with expandable Agent Thought/Tool Trace accordions.
   - Citations drawer showing source document, page, and confidence score.
   - Knowledge Admin Studio: Drag-and-drop document upload (PDF, Word, Excel, CSV, Video), file enable/disable toggle, and Q&A override management.
   - MCP Server & Tool Inspector dashboard.
2. Orchestrator Agent: ReAct/Plan-and-Execute reasoning loop, loop limit controls, and multi-turn state management.
3. RAG as a Tool: Modular `knowledge_base_search` tool featuring Docling parsing, hybrid search (pgvector + BM25), Reciprocal Rank Fusion, and CrossEncoder reranker.
4. MCP Gateway: Python MCP SDK client supporting stdio and SSE transports, dynamic tool discovery (tools/list), and translation into LLM function schemas.
5. Multi-Tool Calling: Support parallel tool execution and sequential tool chaining.
6. API Contracts: Streaming SSE endpoint (/api/chat/stream) emitting token events, tool-start, tool-result, and citation events.
```

### Step 3: Clarification & Alignment
```text
/speckit.clarify Review the full-stack specification and constitution. Ask clarifying questions on any missing edge cases, UI preferences (Next.js App Router vs Vite SPA), initial MCP servers, and deployment choices before planning.
```

### Step 4: Architecture Plan
```text
/speckit.plan Generate plan.md with complete full-stack architectural diagrams, frontend component hierarchy, backend state models, directory structure, and component interaction flows.
```

### Step 5: Tasks Breakdown
```text
/speckit.tasks Break down plan.md into an atomic, dependency-ordered tasks.md checklist covering both Frontend (React/Next.js) and Backend (FastAPI, Agent, RAG, MCP) with clear acceptance criteria.
```

### Step 6: Implementation
```text
/speckit.implement Start executing Task 1 from tasks.md.
```
