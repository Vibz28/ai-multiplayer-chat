# AI Multiplayer Chat Infrastructure

This repository implements a localhost-first, production-parity-capable infrastructure for a chat-style LLM system with:

- Separate backend API/WebSocket service
- Separate LangGraph runtime service
- Persistent application ID <-> LangGraph thread ID mapping
- Streaming content/reasoning/status relays over WebSocket
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
