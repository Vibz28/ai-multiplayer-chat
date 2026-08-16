# Product Rethink: From Socket Lab to Digital Worker

## The Roast

### Product management

The old application had no user job. It was a manual validation harness wearing a product-shaped coat. “Create an application ID, resolve a thread, connect profiles, choose include-AI, select delivery mode, inspect traces” describes the implementation, not a reason for a person to return. The interface made users assemble the demo before they could experience it.

The multiplayer claim was also backwards. One browser impersonated several users and opened several sockets. Real multiplayer means several people can leave, reconnect, share context, and review one worker's output from their own devices.

### Technical lead

The system uses three databases and three application services to produce a chat response, yet the room hub and generation lock are in one Python process. Adding a second backend replica splits presence and permits concurrent runs in the same room. The architecture spent complexity on storage topology while leaving the actual coordination primitive non-distributed.

The 1,196-line React controller combined persistence, REST, socket lifecycle, event reduction, test simulation, identity editing, presentation summaries, and diagnostics. The 1,345-line stylesheet then tried to make every internal control equally important. Neither had a coherent domain boundary.

### System administration

Every database and service was published on all host interfaces with development credentials. The deployment docs called this production-parity-capable while omitting TLS termination, secret rotation, backups, resource limits, log retention, queue durability, and a WebSocket-aware scaling plan. ECS update scripts are not an operating model.

### Security engineering

Knowing an `application_id` granted session reads, history reads, checklist reads, and WebSocket access. A caller could assert any `profile_id` and any role, including `admin`. Direct-message privacy depended on those unverified strings. The UI exposed model reasoning and trace identifiers to every room participant. CORS allowed credentials even though the service had no identity layer.

Container boundaries were cosmetic: application processes ran as root, retained default Linux capabilities, and had no `no-new-privileges` protection. The worker did not have a defined distinction between workspace writing and repository administration.

### QA

The tests verified event ordering in one happy-path process. They did not cover unauthorized room access, reconnect behavior, duplicate events, stale capabilities, horizontal scaling, mobile interaction, keyboard behavior, slow consumers, oversized streams, or recovery during an agent run. The one frontend test checked three headings.

### UX design

The old design was an infrastructure dashboard in dark navy: three rails, cards inside cards, status pills, badges, IDs, profile impersonation, an incognito switch, a control studio, a burst-test button, and a reasoning trace. It asked ordinary people to understand system nouns before they could send a sentence. On mobile, the dashboard became a long stack rather than a designed phone experience.

## The New Job

> Give a trusted worker an outcome, keep collaborators in the conversation, and receive finished work with a clear review boundary.

Fieldwork now treats the worker as the product and WebSockets as invisible plumbing.

- The first screen explains who Moss is, where work happens, and who retains control.
- Starting a room creates and resolves infrastructure in one action.
- One browser represents one person; an invite opens the same persistent room elsewhere.
- Socket reconnection and room persistence happen automatically.
- Worker states use human language instead of transport or model terms.
- The checklist is “current assignment,” not a diagnostics panel.
- Reasoning, trace IDs, run IDs, delivery modes, and concurrency tests are absent from the main experience.
- Harness choice and technical details live in a secondary sheet.
- The composer is built for a phone and includes browser dictation.
- Telegram adds native iPhone voice-note assignment without opening an inbound port.

## Product Limits

This pull request proves the room, capability, streaming, persistence, phone bridge, downloadable deliverables, visual product direction, and real harness dispatch. Moss Cloud uses cloud models only. Selecting Claude Code, Codex, OpenCode, or Pi invokes that pinned binary in its provider-specific credential runtime; diagnostics record both the requested and executed harness.

The Compose demo still uses persistent room workspaces and long-lived runtime services rather than one disposable container per assignment. It has no repository checkout/publisher, browser automation, deployment authority, or privileged approval executor. Those remain production supervisor responsibilities described in `DIGITAL_WORKER_ARCHITECTURE.md`.
