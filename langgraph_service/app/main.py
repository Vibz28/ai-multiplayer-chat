from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import asyncpg
from fastapi import FastAPI, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import BaseModel
from redis.asyncio import Redis

from app.agent import coerce_message_content, get_compiled_graph
from app.config import get_settings


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
    captured_at: datetime


class RuntimeState:
    def __init__(self) -> None:
        self.postgres_pool: asyncpg.Pool | None = None
        self.redis_client: Redis | None = None
        self.agent_graph: Any | None = None


state = RuntimeState()
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.postgres_pool = await asyncpg.create_pool(dsn=settings.postgres_dsn)
    state.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    state.agent_graph = get_compiled_graph()

    async with state.postgres_pool.acquire() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                application_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    await state.redis_client.ping()

    yield

    if state.redis_client is not None:
        await state.redis_client.aclose()
    if state.postgres_pool is not None:
        await state.postgres_pool.close()


app = FastAPI(title=settings.api_title, lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    postgres_ok = False
    redis_ok = False

    if state.postgres_pool is not None:
        try:
            async with state.postgres_pool.acquire() as connection:
                await connection.fetchval("SELECT 1")
            postgres_ok = True
        except Exception:
            postgres_ok = False

    if state.redis_client is not None:
        try:
            await state.redis_client.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

    agent_ok = state.agent_graph is not None
    status = "ok" if postgres_ok and redis_ok and agent_ok else "degraded"
    return HealthResponse(
        status=status,
        checks={"postgres": postgres_ok, "redis": redis_ok, "agent_graph": agent_ok},
    )


@app.post("/threads", response_model=ThreadResponse, status_code=201)
async def create_or_get_thread(request: ThreadRequest) -> ThreadResponse:
    if state.postgres_pool is None:
        raise HTTPException(status_code=503, detail="Postgres pool not initialized")

    async with state.postgres_pool.acquire() as connection:
        existing = await connection.fetchrow(
            "SELECT thread_id, application_id, created_at FROM threads WHERE application_id = $1",
            request.application_id,
        )
        if existing:
            thread_id = str(existing["thread_id"])
            created_at = existing["created_at"]
        else:
            thread_id = f"thread_{uuid4()}"
            created_at = datetime.now(UTC)
            try:
                await connection.execute(
                    "INSERT INTO threads(thread_id, application_id, created_at) VALUES ($1, $2, $3)",
                    thread_id,
                    request.application_id,
                    created_at,
                )
            except asyncpg.UniqueViolationError:
                fallback = await connection.fetchrow(
                    "SELECT thread_id, application_id, created_at FROM threads WHERE application_id = $1",
                    request.application_id,
                )
                if fallback is None:
                    raise
                thread_id = str(fallback["thread_id"])
                created_at = fallback["created_at"]

    if state.redis_client is not None:
        await state.redis_client.set(
            f"thread:{thread_id}:last_seen",
            datetime.now(UTC).isoformat(),
        )

    return ThreadResponse(
        thread_id=thread_id,
        application_id=request.application_id,
        created_at=created_at,
    )


@app.post("/agent/runs", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    if state.agent_graph is None:
        raise HTTPException(status_code=503, detail="Agent graph not initialized")

    try:
        result = await state.agent_graph.ainvoke(
            {
                "messages": [{"role": "user", "content": request.message}],
                "application_id": request.application_id,
                "thread_id": request.thread_id,
                "profile_id": request.profile_id,
            },
            config={
                "configurable": {
                    "thread_id": request.thread_id,
                    "application_id": request.application_id,
                    "profile_id": request.profile_id,
                }
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent invocation failed: {exc}",
        ) from exc

    messages: list[BaseMessage] = result.get("messages", [])
    assistant_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
    tool_messages = [coerce_message_content(msg.content) for msg in messages if isinstance(msg, ToolMessage)]

    if not assistant_messages:
        raise HTTPException(status_code=502, detail="Agent response did not include an assistant message")

    final_message = assistant_messages[-1]
    return AgentRunResponse(
        application_id=request.application_id,
        thread_id=request.thread_id,
        answer_markdown=coerce_message_content(final_message.content),
        tool_messages=tool_messages,
        captured_at=datetime.now(UTC),
    )
