# Phase Plan

## Phase 0: Bootstrap (Current)

- Initialize isolated git repository
- Add core planning and architecture docs
- Prepare feature branch strategy
- Create GitHub repository and GitHub Project board

## Phase 1: Foundation / Infrastructure

- Backend scaffold and health checks
- WebSocket framework and event envelope contract
- DynamoDB Local integration for app/thread mapping
- Compose profiles (`dev` and `prod-parity`)

## Phase 2: LangGraph Integration + Streaming

- Separate LangGraph runtime stack with Postgres and Redis
- Backend<->LangGraph thread lifecycle integration
- Streaming token/reasoning/status relay over WebSocket
- Event normalization and routing by `application_id`

## Phase 3: TypeScript Frontend

- Chat interface + composer + indicators
- Profile/user swap controls for local manual testing
- Streaming content + reasoning panels
- Markdown rendering and Mermaid rendering with fallback
- Session/application visibility and reconnect handling

## Phase 4: Hardening, Testing, Docs

- Unit tests across mapping/event/routing/provider layers
- Integration tests across backend, DynamoDB, LangGraph, WebSocket
- Docker Compose smoke tests
- End-to-end local demo script and runbook
- Known limitations and extension points

## Branch Strategy

- `main`: stable integration branch
- `codex/phase-0-bootstrap`
- `codex/phase-1-foundation`
- `codex/phase-2-streaming-langgraph`
- `codex/phase-3-frontend`
- `codex/phase-4-testing-hardening`

Each phase is delivered with passing tests/build checks before merge.
