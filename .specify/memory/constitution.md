<!--
Sync Impact Report:
- Version change: Unversioned Template -> 1.0.0
- Principles defined:
  - I. Full-Stack Architectural Separation
  - II. Modularity & Domain Isolation
  - III. Asynchronous-First Python Execution
  - IV. Real-Time Streaming & Observability-Driven UX
  - V. End-to-End Strict Type Safety
  - VI. Zero-Trust Security & MCP Tool Isolation
- Added sections:
  - Core Principles
  - Technology Stack & Platform Invariants
  - Development Workflow & Quality Gates
  - Governance
- Removed sections: Template placeholders replaced with concrete project policies
- Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ Aligned (Constitution Check gate verified)
  - .specify/templates/spec-template.md: ✅ Aligned
  - .specify/templates/tasks-template.md: ✅ Aligned
- Follow-up TODOs: None
-->

# AI-Agent-ChatBot Constitution

## Core Principles

### I. Full-Stack Architectural Separation
The application MUST strictly decouple the frontend (Next.js/React, TypeScript) from the backend (FastAPI, Python). The frontend MUST communicate exclusively through well-defined HTTP REST endpoints, Server-Sent Events (SSE) for streaming, or WebSockets. No backend domain logic or direct database connections may leak into the presentation layer, and no frontend-specific rendering state may dictate backend core schemas.

### II. Modularity & Domain Isolation
The backend architecture MUST be strictly partitioned into independent, decoupled domains:
1. **Agent Orchestration Engine**: Manages reasoning, planning, loop limits, and tool routing.
2. **MCP Gateway**: Manages dynamic tool discovery (`tools/list`), connection pooling (stdio/SSE), and execution sandboxing (`tools/call`).
3. **Advanced RAG Core**: Operates as a modular tool (`knowledge_base_search`) handling document ingestion, hybrid vector/BM25 retrieval, RRF, and CrossEncoder reranking.
4. **Data & Storage Services**: Isolated data access layers for PostgreSQL/pgvector and Azure Blob Storage.
Cross-domain coupling MUST occur only through explicit service interfaces and typed data transfer objects.

### III. Asynchronous-First Python Execution
All I/O-bound operations on the backend MUST follow non-blocking asynchronous patterns:
- Database transactions and queries MUST use `asyncpg` connection pools.
- External HTTP and MCP communications MUST use asynchronous clients (`httpx`, `mcp-python-sdk`).
- Multi-tool invocations that do not have data dependencies MUST execute concurrently via `asyncio.gather` to minimize latency.
- CPU-heavy parsing or conversion (e.g., Docling, FFmpeg) MUST run in designated thread pools or background tasks to avoid blocking the async event loop.

### IV. Real-Time Streaming & Observability-Driven UX
The user interface MUST prioritize immediate, transparent, and responsive feedback:
- Agent responses MUST stream incrementally token-by-token using Server-Sent Events (SSE).
- Intermediate reasoning steps, tool invocation statuses, and progress indicators MUST be surfaced in collapsible thought/trace accordions rather than hidden behind spinners.
- Generated statements derived from retrieved knowledge MUST provide clickable citations, source metadata, and confidence metrics.
- The UI MUST be styled cleanly with Tailwind CSS and accessible primitives (shadcn/ui), supporting graceful degradation when streams disconnect.

### V. End-to-End Strict Type Safety
Both sides of the application MUST enforce uncompromising type safety:
- The backend MUST use Pydantic v2 schemas for all request payloads, response bodies, tool arguments, and internal state models.
- The frontend MUST maintain TypeScript types strictly aligned with backend Pydantic models.
- Any change to an API contract or tool schema MUST be reflected synchronously across both backend schemas and frontend types.
- "Any" types, implicit type coercions, and untyped dictionaries across API boundaries are strictly prohibited.

### VI. Zero-Trust Security & MCP Tool Isolation
All external integrations, MCP servers, and file uploads MUST adhere to zero-trust principles:
- Zero hardcoded secrets: All credentials, API keys, connection strings, and tokens MUST be injected through validated environment variables or secure key vaults.
- Model Context Protocol (MCP) servers MUST execute in isolated subprocesses or network boundaries with strict timeout enforcement and circuit breakers.
- User inputs and LLM-generated responses MUST pass through input validation and sanitization guardrails to mitigate prompt injections and data exfiltration.
- File uploads MUST undergo MIME verification, extension validation, and virus/tamper scanning before staging.

## Technology Stack & Platform Invariants

1. **Backend Service**:
   - Python 3.11+
   - FastAPI with Uvicorn
   - Pydantic v2 for data validation
   - asyncpg for asynchronous PostgreSQL connectivity
2. **Frontend Application**:
   - Next.js (App Router) or Vite + React with TypeScript
   - Tailwind CSS with shadcn/ui component architecture
   - Lucide React for consistent UI iconography
   - Native Fetch EventStream / Server-Sent Events client
3. **Storage & Persistence**:
   - PostgreSQL 15+ with `pgvector` extension for dense embeddings and `pg_trgm` for BM25 text search
   - Azure Blob Storage for original documents and extracted media
4. **Intelligence & Tool Calling**:
   - OpenAI (`gpt-4o`, `o3-mini`) and Google Gemini (2.0 Flash/Pro)
   - Official Python `mcp` SDK
   - CrossEncoder for semantic reranking (`sentence-transformers`)

## Development Workflow & Quality Gates

1. **Test-First & Contract Verification**:
   - All MCP tool adapters and RAG functions MUST have comprehensive unit tests.
   - API endpoints MUST have automated contract and integration tests verifying request/response compliance.
2. **Code Quality Gates**:
   - Python code MUST pass static type checking (`mypy` or `pyright`) and strict linting (`ruff`).
   - TypeScript code MUST compile with `strict: true` and zero compiler warnings.
3. **Definition of Done**:
   - A task is considered complete ONLY when:
     1. Associated unit and contract tests pass.
     2. Types are synchronized between backend Pydantic models and frontend TypeScript interfaces.
     3. Error handling, timeouts, and fallbacks are tested.
     4. No new secrets or unsecured endpoints are introduced.

## Governance

1. **Constitutional Authority**:
   - This Constitution represents the supreme architectural and engineering policy of the AI-Agent-ChatBot project.
   - All subsequent specifications, plans, task breakdowns, code implementations, and pull requests MUST comply with these principles.
2. **Amendment Procedure**:
   - Amendments to this Constitution require an explicit justification, a semver version increment, and a comprehensive Sync Impact Report documenting affected templates and artifacts.
3. **Complexity Justification**:
   - Any architectural design introducing additional services, external libraries, or exceptions to these invariants MUST document why simpler alternatives were rejected in the `plan.md` Complexity Tracking section.

**Version**: 1.0.0 | **Ratified**: 2026-11-12 | **Last Amended**: 2026-11-12
