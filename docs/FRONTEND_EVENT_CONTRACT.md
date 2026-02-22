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

- `GET /v1/sessions/{application_id}`
  - Reads existing session mapping.

- `POST /v1/sessions/{application_id}/thread`
  - Resolves/creates the single active LangGraph thread for the application.
  - Returns:
    - `application_id`
    - `langgraph_thread_id`
    - `workflow_id`
    - `langsmith_trace_id`

- `GET /v1/sessions/{application_id}/history?limit=300`
  - Returns canonical thread history from LangGraph persistence (Postgres/Redis-backed).

## WebSocket Endpoint

- `GET ws://<backend>/ws/{application_id}`
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
  "recipient_profile_ids": []
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
  - append `payload.delta` to assistant reasoning panel.

- `content`
  - append `payload.delta` to assistant markdown content.

- `complete`
  - mark active assistant message complete.
  - if available, use `payload.run.run_id` / `payload.run.trace_id`.

- `error`
  - mark stream error state and surface `payload.message`.

- `user_message`
  - render user message with:
    - `delivery_mode`
    - `recipient_profile_ids`
    - `include_ai`

## Multiplayer Behaviors Covered in Phase 3 UI

- user-to-user (direct, no AI)
- user-to-group (thread broadcast, no AI)
- user-to-AI (single sender)
- multi-users-to-AI (concurrent sends; backend serializes generation per application and emits queue/run statuses)

## Manual Validation Checklist

1. Create session and resolve thread.
2. Connect 2+ participants to same application.
3. Send direct no-AI message from one participant to another.
4. Send thread no-AI group message.
5. Send AI-enabled message and verify:
   - `queued/generating/reasoning/completed` states
   - live reasoning/content deltas
6. Trigger concurrent AI burst from multiple participants and verify queueing + sequential completion.
7. Reload history and confirm transcript continuity for same `application_id`.
