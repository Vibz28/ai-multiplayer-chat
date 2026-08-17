from __future__ import annotations

from typing import cast

import pytest
from app.services.websocket_hub import WebSocketHub
from fastapi import WebSocket, WebSocketDisconnect


@pytest.mark.asyncio
async def test_disconnect_never_replaces_generation_lock() -> None:
    hub = WebSocketHub()
    application_id = "app-active-run"
    websocket = cast(WebSocket, object())
    hub._connections[application_id].add(websocket)

    async with hub.generation_guard(application_id):
        active_lock = hub._generation_locks[application_id]
        await hub.disconnect(application_id, websocket)
        assert hub._generation_locks[application_id] is active_lock
        assert await hub.generation_busy(application_id) is True

    assert hub._generation_locks[application_id] is active_lock


@pytest.mark.asyncio
async def test_stale_socket_does_not_abort_room_broadcast() -> None:
    class StaleWebSocket:
        async def send_json(self, event: dict[str, object]) -> None:
            raise WebSocketDisconnect()

    hub = WebSocketHub()
    application_id = "app-stale-socket"
    websocket = cast(WebSocket, StaleWebSocket())
    hub._connections[application_id].add(websocket)

    await hub.emit(application_id, {"type": "status"})

    assert await hub.connection_count(application_id) == 0
