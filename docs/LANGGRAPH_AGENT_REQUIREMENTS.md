# LangGraph Agent Requirements

This document defines the required packages, CLI tooling, and runtime configuration for the LangGraph service used by this project.

## Required Python Packages

Install these in `langgraph_service`:

- `langgraph==1.0.9`
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

- Graph orchestration via LangGraph (`create_react_agent` compiled graph)
- Autonomous tool-call execution via LangChain tools
- Model fallback chain for robustness:
  - primary: `kimi-k2.5:cloud`
  - first fallback: `qwen3-vl:235b-cloud`
  - second fallback: `gpt-oss:20b` (local Ollama)
- Persistent thread registration via Postgres
- Runtime heartbeat/session side-channel via Redis

## Streaming Contract

`langgraph_service` exposes:

- `POST /agent/runs`: single-shot response
- `POST /agent/stream`: NDJSON event stream for backend relay

Event types emitted by `POST /agent/stream`:

- `status`
- `reasoning`
- `content`
- `complete`
- `error`

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
- `LANGGRAPH_OLLAMA_PRIMARY_BASE_URL`
- `LANGGRAPH_OLLAMA_PRIMARY_MODEL`
- `LANGGRAPH_OLLAMA_FALLBACK_CLOUD_BASE_URL`
- `LANGGRAPH_OLLAMA_FALLBACK_CLOUD_MODEL`
- `LANGGRAPH_OLLAMA_FALLBACK_LOCAL_BASE_URL`
- `LANGGRAPH_OLLAMA_FALLBACK_LOCAL_MODEL`
- `LANGGRAPH_AGENT_SYSTEM_PROMPT`
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

- `scripts/langgraph-tui --langgraph-url http://localhost:8080`

Options:

- `--application-id` (default: generated `cli-<id>`)
- `--thread-id` (optional existing thread)
- `--profile-id` (default: `cli-user`)
- `--log-file` (default: `logs/langgraph_tui_events.jsonl`)

In-TUI commands:

- `Enter`: submit prompt
- `/clear`: reset panes
- `/quit` or `/exit`: close client

## Container Runtime

`compose.yaml` configures:

- `langgraph-service` container
- `postgres` (thread persistence)
- `redis` (runtime operational channel)
- LangSmith env forwarding and Ollama endpoint wiring

Start full stack:

- `docker compose up --build`
