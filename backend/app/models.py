from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    profile_id: str | None = None


class SessionResponse(BaseModel):
    application_id: str
    profile_id: str | None
    langgraph_thread_id: str | None
    created_at: datetime
    updated_at: datetime


class ThreadResponse(BaseModel):
    application_id: str
    langgraph_thread_id: str
    updated_at: datetime


class WebSocketInboundMessage(BaseModel):
    type: Literal["ping", "user_message"]
    content: str | None = Field(default=None, max_length=8000)


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
