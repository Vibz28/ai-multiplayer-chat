# Digital Worker Architecture

## Product Boundary

Fieldwork has two planes:

1. The control plane receives assignments, maintains room presence and durable status, and returns business-readable deliverables.
2. The work plane runs an agent harness inside an isolated workspace with narrowly scoped credentials.

The web app and Telegram are control surfaces. They must never become terminals, expose chain-of-thought, or inherit repository administration authority.

## Demo Topology

```text
Browser clients ─┐
                 ├─ signed room capability ─> FastAPI/WebSocket backend
Telegram gateway ┘                              │
      │ outbound polling only                   │ streamed event contract
       └─ cloud transcription                     ▼
                                         LangGraph orchestrator
                                           │              │
                                  credential-free     selected CLI
                                  worker-runtime    provider runtime
                                           │       (one per CLI/auth volume)
                                       workspace + artifact volumes
                                           │
                                      Postgres / Redis
```

Room capabilities are HMAC values bound to an application ID. Browser invite links keep them in the URL fragment so they are not sent to the static web server or referrer headers. They prevent room enumeration and unauthenticated history access; they are not a replacement for user identity, expiry, revocation, or organization policy.

The backend hub is process-local. The demo therefore runs one backend replica. Production must move presence, generation leases, and fan-out to a shared broker before scaling horizontally.

Moss Cloud uses a strict allowlist of Ollama Cloud model identifiers. The host Ollama process is a cloud client; Fieldwork has no local model name or fallback. General tools run in credential-free `worker-runtime`. Claude Code, Codex, OpenCode, and Pi each run in a separate private service that mounts only its own auth volume. Internal APIs require a token not inherited by child processes.

Runtime supervisors have read-only root filesystems and retain only the Linux capabilities required to chown a room workspace and demote a child process. Every room receives a deterministic unprivileged UID and a mode-700 workspace. Provider auth is copied into a mode-700 per-run directory owned by that UID and synced back by the supervisor after token refresh. Model-run processes therefore cannot traverse sibling workspaces, artifact storage, supervisor environment, or another provider's credentials.

The demo workspace is room-scoped, not assignment-scoped. The runtime auto-registers files created under `deliverables/` by a CLI harness; Moss Cloud can explicitly register any completed file. Artifact bytes and metadata are immutable copies, and downloads are proxied through room-capability authorization.

## Production Target

```text
Web / Telegram / approved enterprise chat
                    │
             identity + policy
                    │
          durable job/control queue
                    │ outbound claim/heartbeat
                    ▼
        private persistent worker supervisor
                    │
         one isolated container per assignment
           ├── selected harness adapter
           ├── writable worktree
           ├── browser + evidence recorder
           ├── test/build tools
           └── short-lived task credentials
                    │
        artifact bundle + structured result
                    │
          human review and privileged action
```

Start with a private EC2 worker managed through AWS Systems Manager Session Manager: no public IP, inbound SSH, bastion, or permanent SSH key. A persistent host is useful for browser dependencies, image caches, repository mirrors, and debugging. Add ECS/Fargate later for disposable parallel assignments after work state and artifacts are fully externalized.

Do not create a reverse SSH or public relay to route around enterprise access policy. The worker should claim jobs over an approved outbound channel and return bounded artifacts.

## Harness Adapter Contract

The supervisor exposes one contract independent of Claude Code, Codex, OpenCode, or Pi:

```json
{
  "job_id": "job_...",
  "harness": "opencode",
  "workspace": "/workspace/job_...",
  "prompt": "user outcome",
  "permission_profile": "workspace-writer",
  "resume_cursor": null
}
```

Each adapter must translate native events into:

- `accepted`
- `planning`
- `progress` with a user-safe summary
- `artifact` with immutable metadata
- `approval_required` for a named action
- `completed` with deliverables, verification, and review notes
- `failed` with a recoverable explanation

Native session IDs and resume cursors remain adapter-internal. The supervisor, not the chat client, owns process lifecycle and cancellation.

The demo implements a synchronous subset of this contract: allowlisted argv construction, bounded execution, normalized completion/failure, auto-registration of `deliverables/`, and requested/executed harness diagnostics. It pins Claude Code `2.1.233`, Codex `0.147.0`, OpenCode `1.18.18`, and Pi `0.84.2`. Production still needs cancellation propagation, native progress translation, per-job credentials, and one container per assignment.

## Hard Permission Boundary

Production assignment containers should run as non-root with `no-new-privileges`, all capabilities dropped, no Docker socket, no host home directory, and a read-only root filesystem. The Compose demo uses a minimal-capability runtime supervisor to create room-specific Unix identities, then runs every model-controlled child as that unprivileged identity. Only workspace, artifact, temporary, and provider-specific auth volumes are writable by their designated owners.

The worker receives repository content through a supervisor-controlled checkout. It does not receive organization-owner tokens, repository administration scopes, branch-protection bypass, secret-management permissions, or credentials capable of changing repository settings. A separate publisher service may receive a reviewed patch and create a draft PR using a short-lived installation token with repository-content write permission only.

Required additional controls:

- network egress allowlist and DNS logging
- per-job CPU, memory, process, and wall-clock limits
- immutable event and evidence records
- secret broker with short-lived workload identity
- dependency and artifact scanning
- confirmation for external communication, deployment, purchasing, deletion, or publication
- immediate job cancellation and credential revocation

## Telegram Choice

Telegram is the demo mobile adapter because its Bot API is free, long polling is outbound-only, group chats are natural multiplayer rooms, and iPhone voice notes are first-class attachments. The gateway uses a mandatory numeric chat-ID allowlist. Voice notes use an explicitly configured cloud transcription API; no speech or language model runs locally.

For an enterprise deployment, replace or complement it with the organization's approved single-tenant Teams or Slack bot. Keep that adapter separate from the coding harness, validate tenant/user/channel identity, and render only structured business summaries.
