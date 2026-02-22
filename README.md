# AI Multiplayer Chat Infrastructure

This repository implements a localhost-first, production-parity-capable infrastructure for a chat-style LLM system with:

- Separate backend API/WebSocket service
- Separate LangGraph runtime service
- Persistent application ID <-> LangGraph thread ID mapping
- Streaming content/reasoning/status relays over WebSocket
- Interactive terminal UI client for direct LangGraph runs with streaming diagnostics
- TypeScript frontend for local manual validation

## Source of Truth Prompt

Project goals and scope are derived from:

- `langgraph_infra_coding_agent_system_prompt.md`

## Execution Model

Work is delivered in phased feature branches and merged to `main` after validation.

- Phase 0: repo bootstrap and planning docs
- Phase 1: infrastructure foundation
- Phase 2: LangGraph integration + streaming relay
- Phase 3: TypeScript frontend + Markdown/Mermaid rendering
- Phase 4: testing hardening + smoke/E2E + runbooks

## Current Status

- Repository initialized
- Bootstrap planning docs created
- Architecture decisions approved:
  - Backend: FastAPI
  - Frontend: React + TypeScript + Vite (Bun-managed)
  - LangGraph service: real HTTP integration path with hybrid graph + autonomous tool calls
  - Ollama model policy: `kimi-k2.5:cloud` -> `qwen3-vl:235b-cloud` -> `gpt-oss:20b`

## Key Docs

- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/docs/PHASE_PLAN.md`
- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/docs/ARCHITECTURE_DECISIONS.md`
- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/docs/LANGGRAPH_AGENT_REQUIREMENTS.md`
- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/docs/FRONTEND_EVENT_CONTRACT.md`
- `/Users/vibhorjaney/Downloads/ai-multiplayer-chat/docs/DEPLOYMENT_WORKFLOW.md`

## Stack Operations

Use the script-first workflow:

- `scripts/stack up`
- `scripts/stack smoke`
- `scripts/stack logs backend`
- `scripts/stack down`

AWS publish/deploy helpers:

- `scripts/publish-ecr`
- `scripts/deploy-ecs`
- `scripts/deploy-ec2-compose`

## LangGraph TUI CLI

Run from repository root:

- `scripts/langgraph-tui --langgraph-url http://localhost:8080`

The TUI supports:

- live reasoning and content streaming
- run diagnostics panel with LangSmith-style metadata (run IDs, model selection, token usage, latency, tool calls)
- persistent JSONL run/event logging (`logs/langgraph_tui_events.jsonl` by default)
- server-side persistence/retrieval via Postgres + Redis history APIs (`GET /threads/{thread_id}/history`)
- multi-turn continuity with preserved reasoning/output history across runs
- per-panel scrolling with visible scrollbars (`Tab`, `Shift+Tab`, `Up/Down`, `PgUp/PgDn`, `Home/End`, mouse wheel)
- multi-line prompt composer (`Ctrl+N` to insert newline before submit)
- word/line deletion shortcuts (`Alt+Backspace`, `Ctrl+W`, `Ctrl+U`)
- panel copy helpers (`/copy`, `/copyall`) and terminal-native selection mode (`F2` / `Ctrl+T`)

## Canonical Data Path

- Canonical runtime/thread/run history is persisted in the LangGraph service backing stores:
  - Postgres (`thread_events`, `threads`)
  - Redis (`thread:{thread_id}:history`, `thread:{thread_id}:last_seen`)
- Backend exposes canonical history for clients via:
  - `GET /v1/sessions/{application_id}/history`
- DynamoDB remains metadata-focused for application session mapping:
  - `application_id`, `profile_id`, `role`, `langgraph_thread_id`
  - workflow metadata (`workflow_id`, `langsmith_trace_id`)

## Frontend (Phase 3)

Run locally:

- `cd frontend && bun install`
- `cd frontend && bun run dev`
- `cd frontend && bun run check` (pre-merge: lint, test, build, then type-check)

Phase 3 frontend capabilities:

- multi-user session simulation (many participants on one `application_id`)
- user-to-user/direct and user-to-group messaging
- user-to-AI and multi-user concurrent AI prompts with queued/generating/reasoning/completed indicators
- live transcript and event trace panels for WebSocket debugging
- Markdown rendering with Mermaid rendering + fallback handling
- light and dark themes (toggle in UI, preference persisted locally)
