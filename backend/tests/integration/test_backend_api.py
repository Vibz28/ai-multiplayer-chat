from __future__ import annotations

from collections import defaultdict

from app.dependencies import (
    get_langgraph_client,
    get_mapping_repository,
    get_session_service,
    get_websocket_hub,
)
from app.main import app
from app.repositories.in_memory_mapping_repository import InMemoryMappingRepository
from app.services.session_service import SessionService
from app.services.websocket_hub import WebSocketHub
from fastapi.testclient import TestClient


class InMemoryLangGraphClient:
    def __init__(self) -> None:
        self._threads: dict[str, str] = {}
        self._counters = defaultdict(int)

    async def health(self) -> bool:
        return True

    async def create_thread(self, application_id: str) -> str:
        if application_id in self._threads:
            return self._threads[application_id]
        self._counters[application_id] += 1
        thread_id = f"thread_{application_id}_{self._counters[application_id]}"
        self._threads[application_id] = thread_id
        return thread_id

    async def status_snapshot(self) -> dict[str, str]:
        return {"status": "ok"}

    async def stream_agent_run(
        self,
        *,
        application_id: str,
        thread_id: str,
        profile_id: str | None,
        message: str,
    ):
        yield {
            "type": "reasoning",
            "stream_state": "reasoning",
            "payload": {"delta": f"reasoning for {message}"},
        }
        yield {
            "type": "content",
            "stream_state": "generating",
            "payload": {"delta": f"content for {message}"},
        }
        yield {
            "type": "complete",
            "stream_state": "completed",
            "payload": {"message": "completed"},
        }


def build_test_client() -> TestClient:
    repository = InMemoryMappingRepository()
    langgraph_client = InMemoryLangGraphClient()
    session_service = SessionService(
        repository=repository,
        langgraph_client=langgraph_client,
        application_id_prefix="app",
    )
    hub = WebSocketHub()

    app.dependency_overrides[get_mapping_repository] = lambda: repository
    app.dependency_overrides[get_langgraph_client] = lambda: langgraph_client
    app.dependency_overrides[get_session_service] = lambda: session_service
    app.dependency_overrides[get_websocket_hub] = lambda: hub

    return TestClient(app)


def test_rest_session_and_thread_resolution() -> None:
    with build_test_client() as client:
        create_response = client.post("/v1/sessions", json={"profile_id": "alpha"})
        assert create_response.status_code == 201
        payload = create_response.json()
        assert payload["application_id"].startswith("app_")
        assert payload["profile_id"] == "alpha"
        assert payload["langgraph_thread_id"] is None

        application_id = payload["application_id"]
        read_response = client.get(f"/v1/sessions/{application_id}")
        assert read_response.status_code == 200
        assert read_response.json()["application_id"] == application_id

        thread_response = client.post(f"/v1/sessions/{application_id}/thread")
        assert thread_response.status_code == 200
        thread_payload = thread_response.json()
        assert thread_payload["application_id"] == application_id
        assert thread_payload["langgraph_thread_id"].startswith("thread_")
    app.dependency_overrides.clear()


def test_websocket_event_channels_are_distinct() -> None:
    with build_test_client() as client:
        create_response = client.post("/v1/sessions", json={"profile_id": "beta"})
        application_id = create_response.json()["application_id"]

        with client.websocket_connect(f"/ws/{application_id}") as websocket:
            connection_event = websocket.receive_json()
            assert connection_event["type"] == "connection"

            websocket.send_json({"type": "ping"})
            ping_event = websocket.receive_json()
            assert ping_event["type"] == "status"
            assert ping_event["payload"]["message"] == "pong"

            websocket.send_json({"type": "user_message", "content": "hello"})

            status_event = websocket.receive_json()
            preflight_event = websocket.receive_json()
            reasoning_event = websocket.receive_json()
            content_event = websocket.receive_json()
            complete_event = websocket.receive_json()

            assert status_event["type"] == "status"
            assert preflight_event["type"] == "status"
            assert preflight_event["payload"]["message"] == "langgraph_preflight"
            assert reasoning_event["type"] == "reasoning"
            assert content_event["type"] == "content"
            assert complete_event["type"] == "complete"

            thread_id = status_event["thread_id"]
            assert reasoning_event["thread_id"] == thread_id
            assert content_event["thread_id"] == thread_id
            assert complete_event["thread_id"] == thread_id
            assert "delta" in reasoning_event["payload"]
            assert "delta" in content_event["payload"]

    app.dependency_overrides.clear()
