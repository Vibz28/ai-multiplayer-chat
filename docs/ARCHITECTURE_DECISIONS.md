# Architecture Decisions (User Sign-Off Required)

Per project instruction, architecture choices are explicitly approved by the user before implementation.

## Decision 1: Backend API/WebSocket Stack

- Option A (Recommended): `FastAPI` (Python)
- Option B: `Node.js` (TypeScript)

Reason for recommendation: tighter ecosystem fit with LangGraph and straightforward async WebSocket/event streaming support.

## Decision 2: Frontend Stack

- Option A (Recommended): `React + TypeScript + Vite`
- Option B: another TypeScript stack (user-specified)

Reason for recommendation: fastest maintainable setup for streamed UI state, Markdown/Mermaid rendering, and local testing controls.

## Decision 3: GitHub Repository Visibility

- Option A (Recommended): `private`
- Option B: `public`

Reason for recommendation: infrastructure and environment details are easier to harden before public exposure.

## Decision 4: Initial LangGraph Service Integration Mode

- Option A (Recommended): real HTTP integration with contract-based fallback test double for integration tests
- Option B: test double only in early phases, real integration deferred

Reason for recommendation: ensures deployment-parity behavior while preserving test reliability.
