from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Protocol

import httpx
from pydantic import BaseModel, Field


class LangGraphClientError(Exception):
    """Raised for upstream LangGraph service failures."""


class ThreadHistoryEntry(BaseModel):
    application_id: str
    thread_id: str
    profile_id: str | None
    role: str
    channel: str
    content: str
    run_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class LangGraphClientProtocol(Protocol):
    async def health(self) -> bool:
        ...

    async def create_thread(self, application_id: str) -> str:
        ...

    async def get_thread_history(
        self,
        *,
        thread_id: str,
        limit: int = 200,
    ) -> list[ThreadHistoryEntry]:
        ...

    async def status_snapshot(self) -> dict[str, str]:
        ...

    async def stream_agent_run(
        self,
        *,
        application_id: str,
        thread_id: str,
        profile_id: str | None,
        message: str,
    ) -> AsyncIterator[dict[str, object]]:
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

    async def get_thread_history(
        self,
        *,
        thread_id: str,
        limit: int = 200,
    ) -> list[ThreadHistoryEntry]:
        params = {"limit": max(1, min(limit, 1000))}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    f"{self._base_url}/threads/{thread_id}/history",
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LangGraphClientError("Unable to fetch thread history from LangGraph service") from exc

        payload = response.json()
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            raise LangGraphClientError("LangGraph history response missing entries list")
        parsed: list[ThreadHistoryEntry] = []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            parsed.append(ThreadHistoryEntry.model_validate(raw))
        return parsed

    async def status_snapshot(self) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(f"{self._base_url}/health")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LangGraphClientError("Unable to poll LangGraph service health") from exc

        payload = response.json()
        return {
            "base_url": self._base_url,
            "checked_at": datetime.now(UTC).isoformat(),
            "status": str(payload.get("status", "unknown")),
        }

    async def stream_agent_run(
        self,
        *,
        application_id: str,
        thread_id: str,
        profile_id: str | None,
        message: str,
    ) -> AsyncIterator[dict[str, object]]:
        payload = {
            "application_id": application_id,
            "thread_id": thread_id,
            "profile_id": profile_id,
            "message": message,
        }

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/agent/stream",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise LangGraphClientError("Invalid stream payload from LangGraph service") from exc
                        if not isinstance(event, dict):
                            raise LangGraphClientError("LangGraph stream event must be an object")
                        yield event
        except httpx.HTTPError as exc:
            raise LangGraphClientError("Unable to stream agent response from LangGraph service") from exc
