from datetime import datetime

from app.event_schema import normalize_event


def test_normalize_event_includes_required_fields() -> None:
    event = normalize_event(
        event_type="status",
        application_id="app_123",
        thread_id="thread_123",
        stream_state="idle",
        payload={"message": "ok"},
    )

    assert event["type"] == "status"
    assert event["application_id"] == "app_123"
    assert event["thread_id"] == "thread_123"
    assert event["stream_state"] == "idle"
    assert event["payload"] == {"message": "ok"}
    assert isinstance(datetime.fromisoformat(event["timestamp"]), datetime)
