from datetime import UTC, datetime
from typing import Any


def normalize_event(
    *,
    event_type: str,
    application_id: str,
    payload: dict[str, Any],
    thread_id: str | None = None,
    stream_state: str | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "application_id": application_id,
        "thread_id": thread_id,
        "stream_state": stream_state,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
