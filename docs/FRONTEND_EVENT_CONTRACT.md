# Frontend Event Contract (Phase 3)

This document is the frontend-facing contract for the backend session APIs and WebSocket event stream used by the multiplayer chat UI.

## REST Endpoints

- `POST /v1/sessions`
  - Creates a new `application_id`.
  - Request body:
    - `profile_id?: string`
    - `role?: string`
  - Response:
    - `application_id`
    - `profile_id`
    - `role`
    - `langgraph_thread_id`
    - `workflow_id`
    - `langsmith_trace_id`
     - timestamps
    - `room_token` (returned only at creation; treat as a room capability secret)

- `GET /v1/sessions/{application_id}` with `Authorization: Bearer {room_token}`
  - Reads existing session mapping.

- `POST /v1/sessions/{application_id}/thread` with `Authorization: Bearer {room_token}`
  - Resolves/creates the single active LangGraph thread for the application.
  - Returns:
    - `application_id`
    - `langgraph_thread_id`
    - `workflow_id`
    - `langsmith_trace_id`

- `GET /v1/sessions/{application_id}/history?limit=300` with `Authorization: Bearer {room_token}`
  - Returns canonical thread history from LangGraph persistence (Postgres/Redis-backed).

- `GET /v1/sessions/{application_id}/checklist` with `Authorization: Bearer {room_token}`
  - Returns canonical thread-scoped agent checklist items exposed by LangGraph tooling state.
  - Response includes:
    - `application_id`
    - `langgraph_thread_id`
    - `workflow_id`
    - `langsmith_trace_id`
     - `items[]` with `index`, `text`, `done`

- `GET /v1/sessions/{application_id}/artifacts` with `Authorization: Bearer {room_token}`
  - Lists immutable deliverables registered for the room.
  - `items[]` includes `artifact_id`, `filename`, `title`, `kind`, `media_type`, `size_bytes`, and `sha256`.

- `GET /v1/sessions/{application_id}/model-routes` with `Authorization: Bearer {room_token}`
  - Returns per-harness availability plus the provider, model, and routing mode selected by the platform model router.
  - The frontend disables native harnesses that do not have a compatible platform subscription grant.

- `GET /v1/sessions/{application_id}/artifacts/{artifact_id}/content` with `Authorization: Bearer {room_token}`
  - Downloads one immutable artifact after room-capability validation.

## WebSocket Endpoint

- `GET ws://<backend>/ws/{application_id}` using the `fieldwork.{room_token}` WebSocket subprotocol
  - Multiple participants can connect concurrently to the same `application_id`.
  - Each participant should send `join` after socket open.

### Client -> Backend Messages

- `ping`
```json
{ "type": "ping" }
```

- `join`
```json
{ "type": "join", "profile_id": "alice", "role": "member" }
```

- `leave`
```json
{ "type": "leave", "profile_id": "alice", "role": "member" }
```

- `user_message`
```json
{
  "type": "user_message",
  "content": "hello",
  "profile_id": "alice",
  "role": "member",
  "include_ai": true,
  "delivery_mode": "thread",
  "recipient_profile_ids": [],
  "harness": "langgraph"
}
```

#### Delivery semantics

- `delivery_mode=thread`
  - user content is broadcast to all connected participants in the thread.
- `delivery_mode=direct` + `recipient_profile_ids`
  - user content is routed only to sender + listed recipients.
- `include_ai=false`
  - user-to-user / user-to-group only, no agent run.
- `include_ai=true`
  - backend queues/runs LangGraph generation and relays stream events.

## Backend -> Client Event Envelope

All events are normalized to:

```json
{
  "type": "status|reasoning|content|complete|error|user_message|participant_join|participant_leave|connection",
  "application_id": "app_xxx",
  "thread_id": "thread_xxx",
  "stream_state": "idle|queued|generating|reasoning|completed|error",
  "timestamp": "ISO-8601",
  "payload": {}
}
```

## Stream Event Handling Rules (Frontend)

- `status`
  - `message=queued_for_agent`: show queued state.
  - `message=agent_run_started`: open/create assistant draft turn.
  - `message=pong`: connectivity status refresh.

- `reasoning`
  - treat `payload.delta` as a user-safe progress summary.
  - raw tool inputs, file contents, command output, and chain-of-thought are never included.

- `content`
  - append `payload.delta` to assistant markdown content.

- `complete`
  - mark active assistant message complete.
  - refresh checklist and artifact lists.
  - diagnostics may identify `requested_harness` and `executed_harness`; the main UI does not render internal run/trace IDs.

- `error`
  - mark stream error state and surface `payload.message`.

- `user_message`
  - render user message with:
    - `delivery_mode`
    - `recipient_profile_ids`
    - `include_ai`

## Multiplayer Behaviors Covered in the Fieldwork UI

- one real participant connection per browser or messaging adapter
- persistent room capability links shared between people
- capability values carried in the URL fragment so web-server and referrer logs do not receive them
- automatic reconnect to the same application and canonical history
- group assignments to one worker
- serialized concurrent assignments with human-readable queue states
- real harness dispatch (`langgraph`, `opencode`, `codex`, `claude_code`, or `pi`)

## Manual Validation Checklist

1. Choose **Meet Moss** and verify the room is prepared without exposing IDs.
2. Copy the invite and connect a second browser to the same room.
3. Send an assignment from either participant.
4. Verify both participants receive the same user and worker messages.
5. Verify:
   - `queued/generating/reasoning/completed` states
   - live reasoning/content deltas
6. Reload and confirm history and room continuity.
7. Remove or alter the capability key and verify REST/WebSocket access is rejected.
