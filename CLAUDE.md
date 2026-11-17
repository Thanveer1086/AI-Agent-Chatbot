# CLAUDE.md

Guidance for Claude Code in this repository.

The shared rules for all coding agents live in **AGENTS.md** and are imported below.
Keep project-wide rules there; put only Claude-specific notes in this file.

@AGENTS.md

---

## Most important rules (summary of AGENTS.md)

- **Never run `git add`, `git commit` or `git push`.** The developer reviews and commits manually.
  Read-only git commands (`git status`, `git diff`) are fine.
- **Never commit or print secrets** from `.env` (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `GITHUB_PAT`).
- **Vectors are 1536-dim:** cut embeddings to `[:1536]` and L2-normalise. Use `vector_literal()`
  from `src/core/rag/embeddings.py` for `$n::vector` parameters.

## Spec Kit workflow (Claude integration)

The spec-driven commands are installed in `.claude/skills/`:

`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`

- The current feature is in `specs/001-autonomous-agentic-chatbot/` (spec, plan, tasks, contracts).
- The project constitution is `.specify/memory/constitution.md`; follow it when planning.
- `/speckit-converge` compares the code with the spec and adds missing work to `tasks.md`.

## Where things live (backend)

| Concern | File |
|---|---|
| Settings (all `.env` keys) | `backend/src/config.py` |
| LLM clients, fallback models, streaming, JSON parsing | `backend/src/core/llm.py` |
| Agent nodes (planner, tools, reflection, answer) | `backend/src/core/agent/nodes.py` |
| LangGraph wiring | `backend/src/core/agent/graph.py` |
| SSE chat route, session ownership checks | `backend/src/api/routes_chat.py` |
| MCP client (stdio sessions, HTTP sessions, discovery) | `backend/src/core/mcp/manager.py` |
| Knowledge search (embed → approved answers → hybrid → RRF → rerank) | `backend/src/core/rag/tool.py` |
| Document parsing and chunking | `backend/src/core/rag/ingest.py`, `media_ingest.py` |
| Upload pipeline | `backend/src/core/rag/file_service.py` |
| Guardrails, redaction, untrusted-data fencing | `backend/src/core/security/guardrails.py` |
| Safe filenames and path containment | `backend/src/core/security/paths.py` |
| Tool approval gate (human-in-the-loop) | `backend/src/core/agent/approvals.py`, `src/api/routes_approvals.py` |
| Frontend API calls (adds Bearer token) | `frontend/src/lib/api.ts` |

## Coding conventions

- **Call LLMs only through `src/core/llm.py`** (`complete`, `stream`, `parse_json_object`).
  Don't create provider clients elsewhere; that module handles timeouts, fallbacks and cooldowns.
- **Tool and document output must go through `wrap_untrusted()`** before entering a prompt.
- **Any filename or path from users or the model** must use `safe_filename()` / `resolve_within()`.
- **Session and message routes must check ownership** (`require_session_owner`).
- **Frontend:** use `apiFetch()` from `src/lib/api.ts`, never bare `fetch('/api/...')`.
- **LangGraph reducers:** `tool_execution_history`, `citations` and `intermediate_thoughts` use
  `operator.add`. Nodes must return **only new items**, never old + new.
- **Tools that change things need human approval.** `mcp_manager.requires_approval()` holds any
  MCP tool not annotated `readOnlyHint: true` (or listed in the server's `auto_approve` config).
  The executor stores it in `tool_approvals` (`src/core/agent/approvals.py`); it runs only via
  `POST /api/tools/approvals/{id}/approve`. Never bypass this; new local MCP tools that only read
  must declare `"annotations": {"readOnlyHint": true}`.
- **Streaming tokens** are sent from the answer node with `get_stream_writer()`; the route
  redacts them with `StreamingRedactor`.

## Running and verifying

The backend container mounts `backend/src` but runs **without `--reload`**:

```bash
docker compose restart backend          # after editing Python code
docker compose up -d backend            # after editing .env
docker compose up -d --build backend    # after changing pyproject.toml / Dockerfile
docker compose up -d --build frontend   # after frontend changes
```

Tests are copied into the image at build time (not mounted), and pytest is not in the image:

```bash
docker cp backend/tests/. agent_chatbot_backend:/app/tests/
docker compose exec backend sh -c "pip install -q pytest pytest-asyncio && python -m pytest -q"
```

Frontend checks:

```bash
cd frontend && npx tsc --noEmit && npx vite build
```

Then use the verification checkpoints in AGENTS.md section 5.

## Known gotchas on this machine

- **A native Windows PostgreSQL service uses port 5432.** Docker's DB is mapped with
  `DB_PORT_BIND` (default `5432`). Binding `127.0.0.1:5432` fails; use e.g. `127.0.0.1:5433`.
- **Gemini models can return 503/429.** The default is `gemini-3.5-flash-lite` with fallbacks in
  `GEMINI_FALLBACK_MODELS`; a failing model is skipped for 60s (`llm.py`).
- **The backend image is ~3.4 GB** because of the reranker and Docling (`INSTALL_ML=true`).
  Downloaded models are cached in the `hf_cache` volume.
- **`.gitignore` only ignores the top-level `/lib/`** so that `frontend/src/lib/` is tracked.
- **Windows shell:** prefer forward slashes; `/tmp` is not visible to Windows `curl`.
