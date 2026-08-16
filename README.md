# Fieldwork

Fieldwork is a small, multiplayer digital-worker demo. A group shares one persistent room with an AI worker named Moss. People can hand off work, watch a human-readable plan develop, leave, reconnect, and review the result together without seeing a socket debugger or an observability dashboard.

The repository demonstrates the control-plane bones of a larger system:

- persistent rooms protected by signed capability links
- WebSocket presence, reconnection, queued work, and streamed responses
- canonical thread history and work checklists
- credential-free workspace tools in a private worker container
- one credential-isolated runtime per real Codex, Claude Code, OpenCode, and Pi adapter
- an optional Telegram bridge for text and cloud-transcribed iPhone voice notes
- downloadable, immutable room deliverables

Moss Cloud runs LangGraph through Ollama's cloud service using `kimi-k2.7-code:cloud` with `gpt-oss:120b-cloud` as its cloud fallback. There is no local model fallback, and the stack never loads local Ollama model weights. Its tool suite can search, read, hash-safely edit, run bounded argv-only commands, fetch public web pages, maintain a checklist, and register immutable artifacts. The CLI adapters execute the selected signed-in harness against the same room workspace.

## Try It

Requirements: Docker Desktop and an Ollama client signed in for Ollama Cloud. The Ollama process is only the cloud API client; do not pull or run a local model for Fieldwork.

```bash
scripts/stack up
scripts/stack smoke
```

The stack script creates ignored, mode-600 random values for the room, LangGraph, and runtime service secrets in `.env` when they are absent. Direct `docker compose` use must set `FIELDWORK_ROOM_TOKEN_SECRET`, `FIELDWORK_LANGGRAPH_TOKEN`, and `FIELDWORK_RUNTIME_TOKEN` explicitly.

Open `http://localhost:5173`, choose **Meet Moss**, and copy the room invite into another browser. Both clients join the same room and receive the same worker stream. The room ID is not sufficient by itself; the invite also contains a signed capability key. For a physical phone, build with phone-reachable `VITE_BACKEND_HTTP_URL`/`VITE_BACKEND_WS_URL`, add the public frontend origin to `BACKEND_CORS_ALLOWED_ORIGINS`, and terminate public traffic with TLS.

Useful commands:

```bash
scripts/stack status
STACK_LOG_FOLLOW=0 scripts/stack logs backend
scripts/stack down
```

## Harness Sign-In

Moss Cloud works without harness credentials. To use a CLI adapter, sign in once inside its dedicated persistent auth volume:

```bash
scripts/stack auth codex
scripts/stack auth claude
scripts/stack auth opencode
scripts/stack auth pi
```

Codex uses OpenAI's first-party ChatGPT subscription login. Claude Code uses Anthropic's first-party subscription login; on macOS, container login or `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` is required because host Keychain credentials cannot be mounted. OpenCode and Pi are third-party clients; review provider terms before connecting a subscription. Never expose a personal subscription-backed runner as a public or multi-tenant service.

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
| `langgraph-service` | Cloud-model orchestration, normalized streams, history, and checklist state |
| `worker-runtime` | Credential-free search/read/edit/exec/web/artifact tools |
| `codex-runtime`, `claude-runtime`, `opencode-runtime`, `pi-runtime` | One pinned CLI adapter and one dedicated auth volume per provider |
| `telegram-gateway` | Optional allowlisted text/voice bridge using outbound polling |
| `postgres` | Canonical thread and run history |
| `redis` | Runtime history cache and heartbeat state |
| `dynamodb-local` | Local application-to-thread metadata mapping |

## Security Posture

The local Compose stack binds every published port to `127.0.0.1`, keeps LangGraph internal-only, applies `no-new-privileges`, and gives runtime supervisors read-only root filesystems. A runtime supervisor retains only `CHOWN`, `DAC_OVERRIDE`, `SETUID`, and `SETGID` so it can assign each room a distinct mode-700 workspace UID and demote every model-run process before launch. General commands have no auth volume. Each CLI runtime mounts only its own provider auth volume, copies only the required credential files into a room-UID run directory, and syncs token refresh after exit. Artifacts use the same room UID with mode-700 directories. No runtime receives the Docker socket, host home, SSH keys, or repository administration credentials. Random internal service tokens protect runtime and LangGraph APIs; room REST calls use bearer authorization and WebSockets use a subprotocol so capabilities do not appear in request URLs.

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
