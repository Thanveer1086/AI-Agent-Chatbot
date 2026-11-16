# Tasks: Autonomous Agentic Chatbot with MCP Tools, Advanced RAG, and Modern UI

**Input**: Design documents from `/specs/001-autonomous-agentic-chatbot/`  
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.  

---

## Format: `[ID] [P?] [Story] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to ([US1], [US2], [US3], [US4], [US5])
- All tasks reference explicit file paths across `backend/` and `frontend/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, directory structure, dependencies, and linting configuration

- [X] T001 Create full-stack project directory structure per implementation plan (`backend/`, `frontend/`, `mcp_servers/`, `storage/`)
- [X] T002 [P] Initialize Python backend configuration in `backend/pyproject.toml` with FastAPI, LangGraph, Pydantic v2, asyncpg, mcp, and docling dependencies
- [X] T003 [P] Initialize Vite React TypeScript project in `frontend/package.json` with Tailwind CSS, shadcn/ui primitives, and Lucide icons
- [X] T004 [P] Configure environment template in `.env.example` and backend Pydantic settings validator in `backend/src/config.py`
- [X] T005 [P] Configure frontend styling and build pipeline in `frontend/vite.config.ts` and `frontend/tailwind.config.js`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core database schema, connection pooling, authentication, and base API routing

**⚠️ CRITICAL**: Must complete before any user story can be implemented.

- [X] T006 Setup PostgreSQL database schema with `uuid-ossp`, `vector(1536)` HNSW cosine index, and `pg_trgm` BM25 indexes in `backend/src/core/db/schema.sql`
- [X] T007 Implement asyncpg database connection pool manager and lifespan hooks in `backend/src/core/db/session.py`
- [X] T008 [P] Implement dual-mode JWT authentication handler with `DEV_AUTH_BYPASS` support in `backend/src/core/security/auth.py`
- [X] T009 [P] Implement input/output sanitization and prompt injection guardrails in `backend/src/core/security/guardrails.py`
- [X] T010 [P] Implement Azure Blob Storage client with local disk dev fallback in `backend/src/core/db/blob.py`
- [X] T011 Create main FastAPI application entrypoint with CORS, lifespan, and router aggregation in `backend/src/main.py`
- [X] T012 [P] Define core frontend TypeScript interfaces matching backend models in `frontend/src/types/chat.ts` and `frontend/src/types/admin.ts`
- [X] T013 Setup base frontend application layout and navigation shell in `frontend/src/App.tsx` and `frontend/src/main.tsx`

**Checkpoint**: Foundation ready — User Story 1 implementation can now begin.

---

## Phase 3: User Story 1 - Real-Time Agentic Querying & Citations (Priority: P1) 🎯 MVP

**Goal**: Deliver an end-to-end conversational experience with real-time SSE token streaming, transparent LangGraph reasoning traces, and verifiable source citations.

**Independent Test**: Submit a question to `/api/chat/stream` via curl or the UI; observe streaming tokens, an expanded thought trace accordion showing retrieval latency, and clickable citation preview badges.

### Implementation for User Story 1

- [X] T014 [P] [US1] Define LangGraph `AgentState` schema and intermediate trace structures in `backend/src/core/agent/state.py`
- [X] T015 [P] [US1] Implement dense vector similarity and BM25 hybrid search query functions in `backend/src/core/rag/hybrid.py`
- [X] T016 [P] [US1] Implement Reciprocal Rank Fusion (RRF) algorithm in `backend/src/core/rag/fusion.py`
- [X] T017 [US1] Implement CrossEncoder semantic reranker integration (`ms-marco-MiniLM-L-6-v2`) in `backend/src/core/rag/reranker.py` (depends on T016)
- [X] T018 [US1] Wrap the hybrid search, RRF fusion, and reranker into the callable `knowledge_base_search` tool in `backend/src/core/rag/tool.py` (depends on T015, T017)
- [X] T019 [US1] Implement LangGraph planning, tool execution, and reflection graph nodes in `backend/src/core/agent/nodes.py` (depends on T014, T018)
- [X] T020 [US1] Compile the complete LangGraph `StateGraph` with PostgreSQL checkpointer in `backend/src/core/agent/graph.py` (depends on T019)
- [X] T021 [US1] Implement the Server-Sent Events (SSE) streaming route `POST /api/chat/stream` in `backend/src/api/routes_chat.py` (depends on T020)
- [X] T022 [P] [US1] Implement frontend SSE streaming consumer hook in `frontend/src/hooks/useSSEChat.ts`
- [X] T023 [P] [US1] Implement collapsible Thought Trace accordion component in `frontend/src/components/chat/ThoughtAccordion.tsx`
- [X] T024 [P] [US1] Implement interactive Citation Drawer preview component in `frontend/src/components/chat/CitationDrawer.tsx`
- [X] T025 [US1] Assemble full Chat Workspace view with message stream and markdown rendering in `frontend/src/components/chat/ChatContainer.tsx` (depends on T022, T023, T024)

**Checkpoint**: User Story 1 (MVP) is fully functional and testable independently.

---

## Phase 4: User Story 2 - Knowledge Ingestion & Document Lifecycle (Priority: P1)

**Goal**: Ingest multi-format documents (PDF, Word, Excel, CSV, Video transcripts), generate dense/sparse vectors, and manage active document availability.

**Independent Test**: Upload a PDF via Knowledge Admin Studio; verify chunk count in PostgreSQL and toggle the document disabled to confirm it is excluded from search results.

### Implementation for User Story 2

- [X] T026 [P] [US2] Implement Docling-based document parser and structure-aware chunking utility in `backend/src/core/rag/ingest.py`
- [X] T027 [P] [US2] Implement tabular row chunker (CSV, Excel) and video audio extractor in `backend/src/core/rag/media_ingest.py`
- [X] T028 [US2] Implement atomic upload rollback and transactional file metadata persistence in `backend/src/core/rag/file_service.py` (depends on T026, T027)
- [X] T029 [US2] Implement multipart file upload endpoint `POST /api/upload_file` in `backend/src/api/routes_files.py` (depends on T028)
- [X] T030 [P] [US2] Implement file listing, toggle status, and delete endpoints in `backend/src/api/routes_files.py`
- [X] T031 [P] [US2] Implement drag-and-drop document uploader component in `frontend/src/components/admin/FileUploader.tsx`
- [X] T032 [P] [US2] Implement document management data table with enable/disable switch in `frontend/src/components/admin/FileTable.tsx`
- [X] T033 [US2] Assemble Knowledge Admin Studio page in `frontend/src/components/admin/KnowledgeStudio.tsx` (depends on T031, T032)

**Checkpoint**: User Stories 1 and 2 operate cohesively (ingest documents, then query them via agent).

---

## Phase 5: User Story 3 - Multi-Tool Execution via MCP (Priority: P2)

**Goal**: Enable the agent to dynamically discover and execute external tools via Model Context Protocol (stdio/SSE), supporting parallel and sequential multi-tool calls.

**Independent Test**: Connect the bundled filesystem and database MCP servers; ask a query requiring both document retrieval and database inspection; verify parallel execution in the thought trace.

### Implementation for User Story 3

- [X] T034 [P] [US3] Create bundled reference Filesystem stdio MCP server in `mcp_servers/filesystem/server.py`
- [X] T035 [P] [US3] Create bundled reference PostgreSQL Database stdio MCP server in `mcp_servers/database/server.py`
- [X] T036 [US3] Implement dynamic MCP server discovery (`tools/list`) and connection lifecycle in `backend/src/core/mcp/manager.py` (depends on T034, T035)
- [X] T037 [P] [US3] Implement MCP JSON Schema to OpenAI/Gemini function call adapter in `backend/src/core/mcp/adapters.py`
- [X] T038 [US3] Implement parallel tool execution engine (`asyncio.gather`) with 15s timeout and circuit breaker in `backend/src/core/mcp/executor.py` (depends on T036, T037)
- [X] T039 [US3] Wire MCP tools dynamically into the LangGraph tool dispatch node in `backend/src/core/agent/nodes.py` (depends on T038)
- [X] T040 [US3] Surface parallel tool execution badges and status indicators in `frontend/src/components/chat/ThoughtAccordion.tsx` (depends on T039)

**Checkpoint**: Agent can execute both internal RAG search and external MCP tools in parallel.

---

## Phase 6: User Story 4 - Answer Review, Overrides & User Feedback (Priority: P2)

**Goal**: Allow administrators to publish authoritative answer overrides into an approved QA vector collection and track user satisfaction ratings.

**Independent Test**: Submit a thumbs-down rating on a chat message; draft and publish an answer override; submit the same question and verify the approved answer is returned.

### Implementation for User Story 4

- [X] T041 [P] [US4] Implement user feedback submission endpoint `POST /api/submit/feedback` in `backend/src/api/routes_admin.py`
- [X] T042 [P] [US4] Implement answer drafting and embedding override endpoint `POST /api/override_answer` in `backend/src/api/routes_admin.py`
- [X] T043 [US4] Update LangGraph retrieval node to query `approved_answers` concurrently with document chunks in `backend/src/core/agent/nodes.py` (depends on T042)
- [X] T044 [P] [US4] Implement feedback rating thumbs up/down buttons on messages in `frontend/src/components/chat/MessageItem.tsx`
- [X] T045 [P] [US4] Implement Answer Override Studio interface in `frontend/src/components/admin/AnswerOverrideStudio.tsx`

**Checkpoint**: Human-in-the-loop review and answer override lifecycle is fully functional.

---

## Phase 7: User Story 5 - MCP Server & Tool Inspector Dashboard (Priority: P3)

**Goal**: Provide operational visibility into connected MCP servers, schema definitions, connection health, and invocation latency.

**Independent Test**: Open the MCP Inspector tab; verify server status badges (Online), view tool argument schemas, and trigger a test tool reload.

### Implementation for User Story 5

- [X] T046 [P] [US5] Implement MCP server listing and live health check endpoints `GET /api/mcp/servers` and `GET /api/mcp/tools` in `backend/src/api/routes_mcp.py`
- [X] T047 [P] [US5] Implement MCP runtime re-discovery trigger endpoint `POST /api/mcp/reload` in `backend/src/api/routes_mcp.py`
- [X] T048 [US5] Implement MCP Server & Tool Inspector dashboard in `frontend/src/components/admin/MCPInspector.tsx` (depends on T046, T047)

**Checkpoint**: All 5 user stories are complete and operational.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Multi-container Docker Compose packaging, documentation, and end-to-end verification

- [X] T049 [P] Create multi-stage production Dockerfile for backend in `backend/Dockerfile`
- [X] T050 [P] Create multi-stage Nginx production Dockerfile for frontend in `frontend/Dockerfile`
- [X] T051 Create unified multi-container orchestration configuration in `docker-compose.yml` (depends on T049, T050)
- [X] T052 [P] Implement end-to-end integration test suite in `backend/tests/integration/test_e2e_flow.py`
- [X] T053 Execute all 5 verification scenarios from `specs/001-autonomous-agentic-chatbot/quickstart.md` and document results

---

## Dependencies & Execution Order

```
Phase 1: Setup (T001-T005)
    │
    ▼
Phase 2: Foundational (T006-T013) ──► BLOCKS ALL USER STORIES
    │
    ├───────────────────────────────────────────────────────┐
    ▼                                                       ▼
Phase 3: US1 - Real-Time Chat MVP (T014-T025)     Phase 4: US2 - Knowledge Ingestion (T026-T033)
    │                                                       │
    └───────────────────────┬───────────────────────────────┘
                            ▼
              Phase 5: US3 - MCP Tools (T034-T040)
                            │
                            ▼
              Phase 6: US4 - Answer Overrides (T041-T045)
                            │
                            ▼
              Phase 7: US5 - MCP Inspector (T046-T048)
                            │
                            ▼
              Phase 8: Polish & Docker Compose (T049-T053)
```

---

## Parallel Execution Opportunities

- **Setup & Foundational**:
  - `T002` (Python backend) can run in parallel with `T003` (Vite frontend) and `T004` (`.env.example`).
  - `T008` (Auth), `T009` (Guardrails), and `T010` (Blob client) can all run concurrently once DB schema (`T006`) is in place.
- **User Story 1 (Chat MVP)**:
  - Backend hybrid search (`T015`), RRF fusion (`T016`), and state schema (`T014`) can be built in parallel.
  - Frontend components (`T022`, `T023`, `T024`) can be built concurrently with backend graph nodes (`T019`).
- **User Story 2 (Ingestion)**:
  - Docling parser (`T026`), Tabular chunker (`T027`), and Frontend Uploader (`T031`) can run in parallel.
- **User Story 3 (MCP)**:
  - Filesystem MCP server (`T034`), Database MCP server (`T035`), and Schema Adapter (`T037`) can run in parallel.

---

## Implementation Strategy: MVP First

1. **Step 1: Setup & Foundation (T001 - T013)**: Build database schema, asyncpg pool, auth bypass, and basic frontend shell.
2. **Step 2: MVP Delivery (User Story 1: T014 - T025)**: Build LangGraph, hybrid RAG tool, SSE streaming, and chat UI. **Stop & validate MVP**.
3. **Step 3: Ingestion Pipeline (User Story 2: T026 - T033)**: Add Docling parsing and Knowledge Admin Studio.
4. **Step 4: Tool Calling Power (User Story 3: T034 - T040)**: Add MCP client gateway and parallel multi-tool calling.
5. **Step 5: Governance & Review (User Story 4: T041 - T045)**: Add answer overrides and feedback loop.
6. **Step 6: Visibility & Packaging (User Story 5 & Polish: T046 - T053)**: Add MCP Inspector and Docker Compose stack.
