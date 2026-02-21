from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import httpx


class LangGraphClientError(Exception):
    """Raised for upstream LangGraph service failures."""


class LangGraphClientProtocol(Protocol):
    async def health(self) -> bool:
        ...

    async def create_thread(self, application_id: str) -> str:
        ...

    async def status_snapshot(self) -> dict[str, str]:
        ...


class LangGraphClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._base_url}/health")
                response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def create_thread(self, application_id: str) -> str:
        payload = {"application_id": application_id}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(f"{self._base_url}/threads", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LangGraphClientError("Unable to create thread via LangGraph service") from exc

        data = response.json()
        thread_id = data.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise LangGraphClientError("LangGraph response missing thread_id")
        return thread_id

    async def status_snapshot(self) -> dict[str, str]:
        return {
            "base_url": self._base_url,
            "checked_at": datetime.now(UTC).isoformat(),
        }
