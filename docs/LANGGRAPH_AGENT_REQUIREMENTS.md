# LangGraph Agent Requirements

This document defines the required packages, CLI tooling, and runtime configuration for the LangGraph service used by this project.

## Required Python Packages

Install these in `langgraph_service`:

- `langgraph==1.0.9`
- `langgraph-prebuilt==1.0.8` (pinned for compatibility with LangGraph 1.0.9)
- `langchain==1.2.10`
- `langsmith==0.7.6`
- `langchain-ollama==1.0.1`
- `langgraph-cli==0.4.12`
- `langsmith-cli==0.3.4`

Service/runtime dependencies:

- `fastapi==0.129.2`
- `uvicorn[standard]==0.41.0`
- `asyncpg==0.31.0`
- `redis==7.2.0`
- `httpx==0.28.1`
- `pydantic-settings==2.13.1`

## Agent Runtime Style

The LangGraph service uses a hybrid model:

- Graph orchestration via LangGraph state graph nodes
- Autonomous ReAct-style tool-call execution via LangChain `create_agent` (LangChain v1 API)
- Workflow hooks around the autonomous node:
  - pre-node: prompt/context preparation
  - autonomous node: dynamic tool usage loop
  - post-node: finalize pipeline stage
- Model fallback chain for robustness:
  - primary: `kimi-k2.7-code:cloud`
  - fallback: `gpt-oss:120b-cloud`
  - local model identifiers and local fallbacks are forbidden
- Agent tooling includes:
  - `get_utc_time`
  - `add_numbers`
  - `describe_session_context`
  - `manage_checklist` (thread-scoped dynamic checklist maintenance tool)
  - `workspace_search` (recursive paths and bounded literal text search)
  - `workspace_read` (paged UTF-8 reads with SHA-256)
  - `workspace_edit` (create and hash-checked replace/overwrite/delete)
  - `workspace_exec` (argv-only bounded command execution in the credential-free runtime)
  - `fetch_web` (bounded public HTTP/HTTPS fetch with private-address rejection)
  - `register_artifact` (immutable review copy and metadata)
- External harness dispatch includes pinned Claude Code, Codex, OpenCode, and Pi adapters; provider identity and model selection are resolved by the platform model router.
- Persistent thread registration via Postgres
- Runtime heartbeat/session side-channel via Redis

## Prompt Management (LangSmith Hub Compatible)

The system prompt is managed as a LangSmith/LangChain-serializable YAML manifest:

- local manifest path:
  - `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/langgraph_service/agent_prompts/system_prompt.yaml`

Runtime loading order:

1. If `LANGGRAPH_AGENT_PROMPT_HUB_IDENTIFIER` is set, try `langsmith.Client.pull_prompt(...)`.
2. On pull failure or when unset, load the local YAML manifest fallback.

The YAML format is Hub-compatible (`lc/type/id/kwargs` manifest shape) and can be pushed/pulled through LangSmith Prompt Hub workflows.

## Streaming Contract

`langgraph_service` exposes:

- `POST /agent/runs`: single-shot response
- `POST /agent/stream`: NDJSON event stream for backend relay
- `GET /threads/{thread_id}/history`: persisted run/message history for CLI and frontend retrieval
- `GET /threads/{thread_id}/checklist`: structured checklist items maintained by `manage_checklist`

Event types emitted by `POST /agent/stream`:

- `status`
- `reasoning`
- `content`
- `complete`
- `error`

Streaming behavior details:

- `content` events are emitted from live `on_chat_model_stream` token chunks (incremental, not post-hoc chunking).
- `reasoning` events are safe progress summaries emitted when tools finish. Raw tool inputs/outputs are not relayed or persisted as reasoning.
- If a run completes without tool invocations, reasoning panes should remain empty by design (`tool_message_count=0`).

## Persistence and Retrieval

Conversation artifacts are persisted server-side so clients are not dependent on local JSON logs:

- Postgres:
  - `threads` table for thread registration
  - `thread_events` table for transcript entries, reasoning output, diagnostics, and errors
- Redis:
  - rolling cache list at `thread:{thread_id}:history`
  - last-seen timestamp at `thread:{thread_id}:last_seen`

The TUI hydrates prior history via `GET /threads/{thread_id}/history` when reconnecting to an existing thread.

Each stream event may include `payload.run` diagnostics with LangSmith-style fields:

- run identity: `run_id`, `trace_id`, `name`, `run_type`, `status`
- tracing context: `langsmith_project`, `langsmith_endpoint`, `langsmith_tracing_enabled`
- model chain: `model_primary`, `model_fallbacks`, `model_selected`, `model_provider`
- usage and timings: `token_usage`, `started_at`, `finished_at`, `latency_ms`
- execution detail: `tool_calls`, `tool_call_count`, message/chunk counters
- session metadata: `application_id`, `thread_id`, `profile_id`

Agent entrypoint:

- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/langgraph_service/app/agent.py`

LangGraph CLI graph config:

- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/langgraph_service/langgraph.json`

## Required Environment Variables

- `LANGGRAPH_POSTGRES_DSN`
- `LANGGRAPH_REDIS_URL`
- `LANGGRAPH_OLLAMA_PRIMARY_MODEL`
- `LANGGRAPH_OLLAMA_FALLBACK_CLOUD_MODEL`
- `LANGGRAPH_MODEL_ROUTER_URL`
- `LANGGRAPH_MODEL_ROUTER_TOKEN`
- `LANGGRAPH_SERVICE_TOKEN`
- `LANGGRAPH_RUNTIME_TOKEN`
- `LANGGRAPH_AGENT_PROMPT_MANIFEST_PATH`
- `LANGGRAPH_AGENT_PROMPT_HUB_IDENTIFIER` (optional)
- `LANGGRAPH_AGENT_SYSTEM_PROMPT_FALLBACK`
- `LANGGRAPH_LANGSMITH_TRACING`
- `LANGGRAPH_LANGSMITH_PROJECT`
- `LANGSMITH_API_KEY`
- `LANGSMITH_ENDPOINT`

## LangSmith Logging and Tracing

Tracing is controlled by:

- `LANGGRAPH_LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY=<your_key>`
- `LANGGRAPH_LANGSMITH_PROJECT=ai-multiplayer-chat`

This captures graph runs, model/tool spans, and execution metadata in LangSmith.

## CLI Workflows

From `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/langgraph_service`:

1. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Validate LangGraph config:
   - `langgraph dev --config langgraph.json`
3. Authenticate/validate LangSmith CLI:
   - `langsmith --help`

## Interactive TUI CLI

A first-party terminal UI client is included for direct LangGraph interaction with reasoning/output streaming and diagnostics panels.

Run from repository root:

- `docker compose exec langgraph-service python -m app.tui_cli --log-file /tmp/langgraph-tui.jsonl`

Options:

- `--application-id` (default: generated `cli-<id>`)
- `--thread-id` (optional existing thread)
- `--profile-id` (default: `cli-user`)
- `--log-file` (default: `logs/langgraph_tui_events.jsonl`)

In-TUI commands:

- `Enter`: submit prompt
- `Tab` / `Shift+Tab`: switch focused panel
- `Up` / `Down`: line scroll in focused panel
- `PgUp` / `PgDn`: page scroll in focused panel
- `Home` / `End`: jump oldest/newest in focused panel
- `Mouse wheel`: scroll focused panel (click panel to focus it)
- `Ctrl+N`: insert newline in multi-line prompt composer
- `/clear`: reset panes
- `/quit` or `/exit`: close client

TUI behavior:

- Multi-turn thread continuity is preserved for repeated prompts under the same `application_id`/`thread_id`.
- Reasoning and output stream panes preserve prior run content instead of clearing on completion.
- Panels render visible scrollbars and clamp content to avoid spillover into neighboring panes.

## Container Runtime

`compose.yaml` configures:

- `langgraph-service` container
- `postgres` (thread persistence)
- `redis` (runtime operational channel)
- LangSmith env forwarding and authenticated model-router wiring

Start full stack:

- `docker compose up --build`
