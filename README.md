# Fieldwork

Fieldwork is a small, multiplayer digital-worker demo. A group shares one persistent room with an AI worker named Moss. People can hand off work, watch a human-readable plan develop, leave, reconnect, and review the result together without seeing a socket debugger or an observability dashboard.

The repository demonstrates the control-plane bones of a larger system:

- persistent rooms protected by signed capability links
- WebSocket presence, reconnection, queued work, and streamed responses
- canonical thread history and work checklists
- credential-free workspace tools in a private worker container
- a platform model router plus real Codex, Claude Code, OpenCode, and Pi execution adapters
- an optional Telegram bridge for text and cloud-transcribed iPhone voice notes
- downloadable, immutable room deliverables

All LLM operations pass through Fieldwork's authenticated model-router plane. Moss Cloud uses `kimi-k2.7-code:cloud` with `gpt-oss:120b-cloud` as its cloud fallback; OpenCode and Pi can use the same OpenAI-compatible cloud route with short-lived run tokens. The router also resolves compatible ChatGPT and Claude subscription grants for native harness integrations. There is no local model fallback, and the stack never loads local model weights. Moss can search, read, hash-safely edit, run bounded argv-only commands, fetch public web pages, maintain a checklist, and register immutable artifacts.

## Try It

Requirements: Docker Desktop and an Ollama client signed in for Ollama Cloud. The Ollama process is only the cloud API client; do not pull or run a local model for Fieldwork.

```bash
scripts/stack up
scripts/stack smoke
```

The stack script creates ignored, mode-600 random values for the room, LangGraph, model-router, and runtime service secrets in `.env` when they are absent. Direct `docker compose` use must set `FIELDWORK_ROOM_TOKEN_SECRET`, `FIELDWORK_LANGGRAPH_TOKEN`, `FIELDWORK_MODEL_ROUTER_TOKEN`, and `FIELDWORK_RUNTIME_TOKEN` explicitly.

Open `http://localhost:5173`, choose **Meet Moss**, and copy the room invite into another browser. Both clients join the same room and receive the same worker stream. The room ID is not sufficient by itself; the invite also contains a signed capability key. For a physical phone, build with phone-reachable `VITE_BACKEND_HTTP_URL`/`VITE_BACKEND_WS_URL`, add the public frontend origin to `BACKEND_CORS_ALLOWED_ORIGINS`, and terminate public traffic with TLS.

Useful commands:

```bash
scripts/stack status
STACK_LOG_FOLLOW=0 scripts/stack logs backend
scripts/stack down
```

## Platform Provider Accounts

Authentication belongs to the platform provider account, not to the harness selector. Register only the integration grants a provider permits, then inspect the router's compatibility view:

```bash
scripts/stack auth chatgpt codex
scripts/stack auth chatgpt opencode
scripts/stack auth chatgpt pi
scripts/stack auth claude claude-code
scripts/stack auth claude pi
scripts/stack auth status
```

The provider account store is one persistent platform volume organized by provider and integration grant. OAuth clients still require their own authorization grant; the router does not copy consumer tokens into incompatible formats or pretend subscription OAuth is a generic API key. ChatGPT Plus/Pro is supported by Codex, OpenCode, and Pi. Claude Pro/Max is supported by Claude Code and Pi; Pi documents that third-party Claude usage can draw billed extra usage, while OpenCode explicitly no longer ships Claude subscription support. Without a compatible subscription grant, OpenCode and Pi use the shared cloud route. Never expose a personal subscription-backed runner as a public or multi-tenant service.

Pinned adapters: Codex `0.147.0`, Claude Code `2.1.233`, OpenCode `1.18.18`, and Pi `0.84.2`.

## Telegram Voice Notes

Telegram was selected for the example phone bridge because its Bot API is free, voice notes are native on iPhone, and long polling creates only outbound connections from the worker host.

1. Create a bot with Telegram's `@BotFather`.
2. Put the bot token, an explicit allowlist of numeric chat IDs, and an `OPENAI_API_KEY` for cloud voice transcription in `.env`.
3. Set `FRONTEND_PUBLIC_URL` to the private URL your phone can reach.
4. Start the optional profile.

```bash
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOWED_CHAT_IDS=123456789 \
FRONTEND_PUBLIC_URL=https://your-private-host.example \
scripts/stack up-telegram
```

Send `/start` to receive the shared workroom link. Send text or an iPhone voice note to assign work. Voice audio is sent to the configured OpenAI transcription model; no transcription model runs locally. Text-only Telegram use does not require the transcription key.

## Services

| Service | Responsibility |
|---|---|
| `frontend` | Phone-first React workroom and persistent WebSocket client |
| `backend` | Capability validation, room presence, queueing, and event normalization |
| `model-router` | Provider account resolution, cloud allowlist, delegated run tokens, and OpenAI/Ollama-compatible proxying |
| `langgraph-service` | Cloud-model orchestration, normalized streams, history, and checklist state |
| `worker-runtime` | Credential-free search/read/edit/exec/web/artifact tools |
| `codex-runtime`, `claude-runtime`, `opencode-runtime`, `pi-runtime` | Isolated pinned CLI execution adapters; model/provider identity is resolved by `model-router` |
| `telegram-gateway` | Optional allowlisted text/voice bridge using outbound polling |
| `postgres` | Canonical thread and run history |
| `redis` | Runtime history cache and heartbeat state |
| `dynamodb-local` | Local application-to-thread metadata mapping |

## Security Posture

The local Compose stack binds every published port to `127.0.0.1`; LangGraph and the model router remain internal-only. The router holds the cloud allowlist and issues short-lived tokens to gateway-backed harness runs. Provider OAuth grants live in one root-owned platform account volume; a runtime supervisor copies only the selected compatible grant into a mode-700 run directory. Runtime supervisors use read-only root filesystems and retain only `CHOWN`, `DAC_OVERRIDE`, `SETUID`, and `SETGID` so each model process runs under a room-specific UID. Immutable artifacts are root-owned broker storage. No runtime receives the Docker socket, host home, SSH keys, or repository administration credentials. Room REST calls use bearer authorization and WebSockets use a subprotocol so capabilities do not appear in request URLs.

This is still a single-user/private demo, not an internet-ready deployment. Workspaces are separated by room but share long-lived runtime containers, and a selected coding harness can read its own credential cache while it runs. Before remote use, provide TLS, rotate `BACKEND_ROOM_TOKEN_SECRET`, put the control plane behind identity, use a managed queue, launch one disposable container per assignment, enforce egress and resource limits, and use short-lived task credentials. Do not use an outbound tunnel to bypass corporate access controls.

## Verification

```bash
cd frontend && bun run check
python3.14 -m pytest
python3.14 -m ruff check .
scripts/stack up
scripts/stack smoke
```

Architecture and product rationale:

- `docs/DIGITAL_WORKER_ARCHITECTURE.md`
- `docs/PRODUCT_RETHINK.md`
- `docs/FRONTEND_EVENT_CONTRACT.md`
