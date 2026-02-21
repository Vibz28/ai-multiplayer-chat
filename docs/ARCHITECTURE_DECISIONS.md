# Architecture Decisions (User Sign-Off Required)

Per project instruction, architecture choices are explicitly approved by the user before implementation.

## Decision 1: Backend API/WebSocket Stack

- Selected: `FastAPI` (Python)

Reason for recommendation: tighter ecosystem fit with LangGraph and straightforward async WebSocket/event streaming support.

## Decision 2: Frontend Stack

- Selected: `React + TypeScript + Vite`
- JS package manager/build tool preference: `Bun` over `npm`

Reason for recommendation: fastest maintainable setup for streamed UI state, Markdown/Mermaid rendering, and local testing controls.

## Decision 3: GitHub Repository Visibility

- Selected: `private`

Reason for recommendation: infrastructure and environment details are easier to harden before public exposure.

## Decision 4: Initial LangGraph Service Integration Mode

- Selected: real HTTP integration with contract-based fallback test double for integration tests
- Additional requirement: include `langgraph`, `langchain`, `langsmith`, and related CLI tooling for graph execution and traceability.

Reason for recommendation: ensures deployment-parity behavior while preserving test reliability.
