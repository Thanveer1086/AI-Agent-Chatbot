# Phase 0 Research: Technical Choices & Architecture Decisions

**Feature**: `001-autonomous-agentic-chatbot`  
**Date**: 2026-11-12  
**Status**: Completed  

---

## 1. Orchestration Engine: LangGraph vs. Custom Async ReAct Loop

### Context & Requirements
The agent requires a cyclic reasoning loop (Plan $\rightarrow$ Tool Selection $\rightarrow$ Execution $\rightarrow$ Reflection $\rightarrow$ Answer), multi-turn conversation memory, loop limit guards (max 5 iterations), and human-in-the-loop overrides.

### Decision
**Adopt LangGraph (Python)** using a stateful `StateGraph` compiled with a PostgreSQL checkpointer (`AsyncPostgresSaver`).

### Rationale
- **Native Cycles & Graph Semantics**: Unlike standard linear chains or DAGs, agentic reasoning is cyclical by nature. LangGraph is built specifically for stateful multi-agent and cyclical graphs.
- **Built-in Persistence**: LangGraph natively supports PostgreSQL checkpointing, allowing conversation state, tool calls, and thought traces to survive server restarts.
- **Controlled Concurrency**: Tool execution nodes in LangGraph can easily dispatch parallel sub-graphs or fan-out tool calls with `asyncio.gather`.
- **Fault-Tolerance**: Built-in retry policies and node-level error handlers make it trivial to enforce the 3-tier safety guard (15s timeout, circuit breaker, graceful fallback).

### Alternatives Considered
- **Custom Async `while` Loop**: Simple to write initially, but rapidly accumulates boilerplate for state management, checkpointing, stream formatting, and error-recovery branching.
- **CrewAI / AutoGen**: Designed for multi-agent persona chatting rather than deterministic low-latency tool orchestration within a FastAPI async service.

---

## 2. Model Context Protocol (MCP) Integration: Python MCP SDK

### Context & Requirements
The agent must dynamically discover (`tools/list`) and execute (`tools/call`) tools from external MCP servers via local `stdio` (subprocesses) and remote `sse` (HTTP) transports.

### Decision
**Adopt the official Python `mcp` SDK (`mcp` library)** with an asynchronous `MCPClientManager` service.

### Rationale
- **Standard Protocol Compliance**: The official `mcp` SDK handles JSON-RPC 2.0 framing, transport negotiation, protocol handshake, and tool listing conforming to the open standard.
- **Dual Transport Support**: `stdio.stdio_client` enables secure local subprocess execution; `sse.sse_client` enables connection to remote distributed microservices.
- **Dynamic Schema Translation**: MCP tools expose JSON Schemas conforming to OpenAPI standards. The `MCPClientManager` directly translates these schemas into OpenAI and Gemini function calling definitions.
- **Sandboxed Execution**: Subprocess lifecycles are monitored with `asyncio.wait_for` to strictly enforce the 15-second per-tool timeout invariant.

### Alternatives Considered
- **Custom JSON-RPC Client**: Prone to protocol drift and edge-case framing bugs as the MCP specification evolves.
- **Hardcoded Tool Wrappers**: Violates dynamic discovery and requires code modifications whenever an external tool changes.

---

## 3. Hybrid Search & Reranking Pipeline

### Context & Requirements
The system must maintain the high-precision retrieval qualities of the legacy Trinity architecture: multi-application filtering, dense semantic search, sparse lexical keyword matching, Reciprocal Rank Fusion, and semantic reranking.

### Decision
**PostgreSQL (`pgvector` + `pg_trgm`) + Reciprocal Rank Fusion (RRF) + CrossEncoder (`sentence-transformers/ms-marco-MiniLM-L-6-v2`)**.

### Rationale
- **pgvector HNSW Indexing**: Cosine similarity (`vector_cosine_ops`) with an HNSW index guarantees sub-50ms vector candidate retrieval over hundreds of thousands of chunks.
- **pg_trgm BM25 Emulation**: Trigram word similarity and GIN indexes provide robust lexical fallback for exact product codes, acronyms, and ticket IDs that semantic embeddings miss.
- **Reciprocal Rank Fusion (RRF)**: Merges ranked lists from dense vector search and BM25 using $RRF\_Score(d) = \sum \frac{1}{k + rank_i(d)}$ with $k=60$, ensuring unbiased candidate scoring.
- **CrossEncoder Semantic Reranker**: Performs joint attention over `(query, passage)` pairs on the top 20 fused candidates to select the top 5 highest-relevance passages for the LLM.

### Alternatives Considered
- **Dedicated Vector DB (Pinecone, Qdrant, Milvus)**: Introduces extra operational complexity and distributed transactions. PostgreSQL with `pgvector` keeps relational metadata, vector chunks, and conversation history in a single ACID-compliant database.
- **BM25 Only or Dense Only**: Fails on domain-specific acronyms (dense alone) or paraphrased natural language questions (BM25 alone).

---

## 4. Real-Time Streaming & Observability Protocol

### Context & Requirements
The frontend needs to render token-by-token generation, show intermediate reasoning thoughts, display tool execution badges, and render citations with preview snippets.

### Decision
**Server-Sent Events (SSE)** via FastAPI's `StreamingResponse` using an event-driven JSON envelope format:
`event: <type>\ndata: <json>\n\n`

### Event Types
1. `thought_step`: Emits the agent's internal planning or reflection step.
2. `tool_start`: Emits the tool name and arguments before execution.
3. `tool_result`: Emits the tool execution output, latency, and status.
4. `token`: Emits individual generated answer tokens.
5. `citation`: Emits grounded references (file, section, relevance score).
6. `done`: Emits final message metadata and closes the stream.
7. `error`: Emits recoverable or terminal error diagnostics.

### Rationale
- **Lightweight & Native**: SSE is supported natively by browser `EventSource` and `fetch(..., { readable: true })` without WebSocket handshake overhead.
- **Firewall & Proxy Friendly**: Works over standard HTTP/1.1 and HTTP/2 without persistent bidirectional socket maintenance.

---

## 5. Frontend UI Architecture: Vite + React SPA

### Context & Requirements
A modern, responsive, high-performance UI offering a streaming chat workspace, expandable thought accordions, document preview drawer, and an admin knowledge dashboard.

### Decision
**Vite + React (TypeScript) + Tailwind CSS + shadcn/ui + Lucide Icons + Zustand + TanStack Query**.

### Rationale
- **Zero Node Runtime in Production**: Compiles down to optimized static assets (`/dist`) served via Nginx or FastAPI static files.
- **Instant Local Dev**: Vite provides sub-second HMR and instant startup.
- **Accessible Design System**: shadcn/ui provides clean, accessible Radix UI primitives (accordions for thought traces, dialogs for uploaders, sheets for citation drawers, and data tables for file management).
- **Zustand State Management**: Lightweight store for managing active chat sessions, streaming tokens, active tool execution chips, and theme toggling.
