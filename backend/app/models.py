from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    profile_id: str | None = None
    role: str | None = Field(default="member", max_length=64)


class SessionResponse(BaseModel):
    application_id: str
    profile_id: str | None
    role: str | None
    langgraph_thread_id: str | None
    workflow_id: str | None
    langsmith_trace_id: str | None
    created_at: datetime
    updated_at: datetime


class ThreadResponse(BaseModel):
    application_id: str
    langgraph_thread_id: str
    workflow_id: str | None
    langsmith_trace_id: str | None
    updated_at: datetime


class HistoryEntryResponse(BaseModel):
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


class SessionHistoryResponse(BaseModel):
    application_id: str
    langgraph_thread_id: str
    profile_id: str | None
    role: str | None
    workflow_id: str | None
    langsmith_trace_id: str | None
    entries: list[HistoryEntryResponse]
    count: int


class ChecklistItemResponse(BaseModel):
    index: int
    text: str
    done: bool


class SessionChecklistResponse(BaseModel):
    application_id: str
    langgraph_thread_id: str
    workflow_id: str | None
    langsmith_trace_id: str | None
    items: list[ChecklistItemResponse]
    count: int


class WebSocketInboundMessage(BaseModel):
    type: Literal["ping", "user_message", "join", "leave"]
    content: str | None = Field(default=None, max_length=8000)
    profile_id: str | None = Field(default=None, max_length=128)
    role: str | None = Field(default="member", max_length=64)
    include_ai: bool = True
    delivery_mode: Literal["thread", "direct"] = "thread"
    recipient_profile_ids: list[str] = Field(default_factory=list, max_length=16)


class EventEnvelope(BaseModel):
    type: str
    application_id: str
    thread_id: str | None
    stream_state: str | None
    timestamp: datetime
    payload: dict[str, Any]


class HealthCheckResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]
