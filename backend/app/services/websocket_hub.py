from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, application_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[application_id].add(websocket)

    async def disconnect(self, application_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._connections.get(application_id)
            if clients is None:
                return
            clients.discard(websocket)
            if not clients:
                self._connections.pop(application_id, None)

    async def emit(self, application_id: str, event: dict[str, object]) -> None:
        async with self._lock:
            targets = list(self._connections.get(application_id, set()))

        stale_connections: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(event)
            except RuntimeError:
                stale_connections.append(websocket)

        if stale_connections:
            async with self._lock:
                clients = self._connections.get(application_id)
                if clients is None:
                    return
                for websocket in stale_connections:
                    clients.discard(websocket)
                if not clients:
                    self._connections.pop(application_id, None)

    async def connection_count(self, application_id: str) -> int:
        async with self._lock:
            return len(self._connections.get(application_id, set()))
