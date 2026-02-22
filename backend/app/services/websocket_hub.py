from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import WebSocket


@dataclass(frozen=True)
class Participant:
    profile_id: str
    role: str
    connected_at: datetime


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._participants: dict[str, dict[WebSocket, Participant]] = defaultdict(dict)
        self._generation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock = asyncio.Lock()

    async def connect(self, application_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[application_id].add(websocket)
            self._participants[application_id].setdefault(
                websocket,
                Participant(
                    profile_id="anonymous",
                    role="member",
                    connected_at=datetime.now(UTC),
                ),
            )

    async def disconnect(self, application_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._connections.get(application_id)
            if clients is None:
                return
            clients.discard(websocket)
            participants = self._participants.get(application_id)
            if participants is not None:
                participants.pop(websocket, None)
                if not participants:
                    self._participants.pop(application_id, None)
            if not clients:
                self._connections.pop(application_id, None)
            if application_id not in self._connections:
                self._generation_locks.pop(application_id, None)

    async def set_participant(
        self,
        application_id: str,
        websocket: WebSocket,
        *,
        profile_id: str,
        role: str,
    ) -> Participant:
        participant = Participant(
            profile_id=profile_id,
            role=role,
            connected_at=datetime.now(UTC),
        )
        async with self._lock:
            self._participants[application_id][websocket] = participant
        return participant

    async def get_participant(self, application_id: str, websocket: WebSocket) -> Participant | None:
        async with self._lock:
            participants = self._participants.get(application_id, {})
            return participants.get(websocket)

    async def participants_snapshot(self, application_id: str) -> list[dict[str, str]]:
        async with self._lock:
            participants = list(self._participants.get(application_id, {}).values())

        by_profile: dict[str, Participant] = {}
        for participant in participants:
            by_profile[participant.profile_id] = participant
        return [
            {
                "profile_id": participant.profile_id,
                "role": participant.role,
                "connected_at": participant.connected_at.isoformat(),
            }
            for participant in by_profile.values()
        ]

    async def emit(self, application_id: str, event: dict[str, object]) -> None:
        async with self._lock:
            targets = list(self._connections.get(application_id, set()))
        await self._send_targets(application_id, targets, event)

    async def emit_to_profiles(
        self,
        application_id: str,
        event: dict[str, object],
        *,
        profile_ids: set[str],
    ) -> None:
        async with self._lock:
            participants = self._participants.get(application_id, {})
            targets = [
                websocket
                for websocket, participant in participants.items()
                if participant.profile_id in profile_ids
            ]
        await self._send_targets(application_id, targets, event)

    async def _send_targets(
        self,
        application_id: str,
        targets: list[WebSocket],
        event: dict[str, object],
    ) -> None:
        if not targets:
            return

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
                    participants = self._participants.get(application_id)
                    if participants is not None:
                        participants.pop(websocket, None)
                if not clients:
                    self._connections.pop(application_id, None)
                    self._participants.pop(application_id, None)
                    self._generation_locks.pop(application_id, None)

    async def connection_count(self, application_id: str) -> int:
        async with self._lock:
            return len(self._connections.get(application_id, set()))

    async def generation_busy(self, application_id: str) -> bool:
        async with self._lock:
            lock = self._generation_locks[application_id]
            return lock.locked()

    @asynccontextmanager
    async def generation_guard(self, application_id: str):
        async with self._lock:
            lock = self._generation_locks[application_id]
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
