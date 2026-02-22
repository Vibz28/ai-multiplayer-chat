from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ThreadRequest(BaseModel):
    application_id: str


class ThreadResponse(BaseModel):
    thread_id: str
    application_id: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class AgentRunRequest(BaseModel):
    application_id: str
    thread_id: str
    profile_id: str | None = None
    message: str


class AgentRunResponse(BaseModel):
    application_id: str
    thread_id: str
    answer_markdown: str
    tool_messages: list[str]
    run: dict[str, Any]
    captured_at: datetime


class AgentStreamEvent(BaseModel):
    type: str
    stream_state: str
    application_id: str
    thread_id: str
    payload: dict[str, Any]
    timestamp: datetime


class ThreadHistoryEntry(BaseModel):
    application_id: str
    thread_id: str
    profile_id: str | None
    role: str
    channel: str
    content: str
    run_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any]
    created_at: datetime


class ThreadHistoryResponse(BaseModel):
    thread_id: str
    entries: list[ThreadHistoryEntry]
    count: int
