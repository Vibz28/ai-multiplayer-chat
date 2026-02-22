from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.history_store import fetch_thread_history, persist_history_entry
from app.runtime import lifespan, postgres_healthy, redis_healthy, settings, state
from app.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    HealthResponse,
    ThreadHistoryEntry,
    ThreadHistoryResponse,
    ThreadRequest,
    ThreadResponse,
)
from app.streaming import agent_event_stream, invoke_agent

app = FastAPI(title=settings.api_title, lifespan=lifespan)

# Backward-compatible alias for unit tests and internal imports.
_agent_event_stream = agent_event_stream


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    postgres_ok = await postgres_healthy()
    redis_ok = await redis_healthy()
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


@app.get("/threads/{thread_id}/history", response_model=ThreadHistoryResponse)
async def get_thread_history(thread_id: str, limit: int = 200) -> ThreadHistoryResponse:
    rows = await fetch_thread_history(thread_id, limit=limit)
    entries = [
        ThreadHistoryEntry(
            application_id=row["application_id"],
            thread_id=row["thread_id"],
            profile_id=row["profile_id"],
            role=row["role"],
            channel=row["channel"],
            content=row["content"],
            run_id=row["run_id"],
            trace_id=row["trace_id"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return ThreadHistoryResponse(
        thread_id=thread_id,
        entries=entries,
        count=len(entries),
    )


@app.post("/agent/runs", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    run_id = f"run_{uuid4()}"
    trace_id = str(uuid4())
    started_at = datetime.now(UTC)

    answer_markdown, tool_messages, run = await invoke_agent(
        request,
        run_id=run_id,
        trace_id=trace_id,
        started_at=started_at,
    )

    await persist_history_entry(
        application_id=request.application_id,
        thread_id=request.thread_id,
        profile_id=request.profile_id,
        role="user",
        channel="transcript",
        content=request.message,
        run_id=run_id,
        trace_id=trace_id,
        metadata={"source": "agent_runs"},
    )
    await persist_history_entry(
        application_id=request.application_id,
        thread_id=request.thread_id,
        profile_id=request.profile_id,
        role="assistant",
        channel="transcript",
        content=answer_markdown,
        run_id=run_id,
        trace_id=trace_id,
        metadata={"source": "agent_runs"},
    )
    if tool_messages:
        await persist_history_entry(
            application_id=request.application_id,
            thread_id=request.thread_id,
            profile_id=request.profile_id,
            role="assistant",
            channel="reasoning",
            content="\n\n".join(tool_messages),
            run_id=run_id,
            trace_id=trace_id,
            metadata={"source": "agent_runs"},
        )
    await persist_history_entry(
        application_id=request.application_id,
        thread_id=request.thread_id,
        profile_id=request.profile_id,
        role="system",
        channel="diagnostics",
        content="run_diagnostics",
        run_id=run_id,
        trace_id=trace_id,
        metadata={"run": run},
    )

    return AgentRunResponse(
        application_id=request.application_id,
        thread_id=request.thread_id,
        answer_markdown=answer_markdown,
        tool_messages=tool_messages,
        run=run,
        captured_at=datetime.now(UTC),
    )


@app.post("/agent/stream")
async def stream_agent_run(request: AgentRunRequest) -> StreamingResponse:
    return StreamingResponse(
        agent_event_stream(request),
        media_type="application/x-ndjson",
    )
