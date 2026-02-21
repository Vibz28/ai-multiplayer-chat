from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from os import getenv
from typing import Any
from uuid import uuid4

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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
    run: dict[str, Any]
    captured_at: datetime


class AgentStreamEvent(BaseModel):
    type: str
    stream_state: str
    application_id: str
    thread_id: str
    payload: dict[str, Any]
    timestamp: datetime


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


def _build_event(
    *,
    event_type: str,
    stream_state: str,
    application_id: str,
    thread_id: str,
    payload: dict[str, Any],
) -> AgentStreamEvent:
    return AgentStreamEvent(
        type=event_type,
        stream_state=stream_state,
        application_id=application_id,
        thread_id=thread_id,
        payload=payload,
        timestamp=datetime.now(UTC),
    )


def _chunk_text(text: str, chunk_size: int = 48) -> list[str]:
    return [text[idx : idx + chunk_size] for idx in range(0, len(text), chunk_size)]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_model_name(message: AIMessage) -> str | None:
    response_metadata = getattr(message, "response_metadata", None)
    if isinstance(response_metadata, dict):
        for key in ("model", "model_name", "model_id"):
            candidate = response_metadata.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        for key in ("model", "model_name", "model_id"):
            candidate = additional_kwargs.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


def _extract_token_usage(assistant_messages: list[AIMessage]) -> dict[str, int]:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    for message in assistant_messages:
        response_metadata = getattr(message, "response_metadata", {})
        usage_payload: dict[str, Any] | None = None

        usage_metadata = getattr(message, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            usage_payload = usage_metadata

        if usage_payload is None and isinstance(response_metadata, dict):
            nested_usage = response_metadata.get("token_usage") or response_metadata.get("usage")
            if isinstance(nested_usage, dict):
                usage_payload = nested_usage

        prompt = 0
        completion = 0
        total = 0

        if isinstance(usage_payload, dict):
            prompt = _to_int(usage_payload.get("input_tokens") or usage_payload.get("prompt_tokens"))
            completion = _to_int(
                usage_payload.get("output_tokens") or usage_payload.get("completion_tokens")
            )
            total = _to_int(usage_payload.get("total_tokens"))

        if isinstance(response_metadata, dict) and prompt == 0 and completion == 0:
            prompt = _to_int(response_metadata.get("prompt_eval_count"))
            completion = _to_int(response_metadata.get("eval_count"))

        if total == 0:
            total = prompt + completion

        prompt_tokens += prompt
        completion_tokens += completion
        total_tokens += total

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _extract_tool_calls(assistant_messages: list[AIMessage]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for message in assistant_messages:
        current_calls = getattr(message, "tool_calls", None)
        if not isinstance(current_calls, list):
            continue
        for call in current_calls:
            if not isinstance(call, dict):
                continue
            args = call.get("args", {})
            tool_calls.append(
                {
                    "id": str(call.get("id", "")),
                    "name": str(call.get("name", "unknown")),
                    "type": str(call.get("type", "tool_call")),
                    "args": args if isinstance(args, dict) else {"value": str(args)},
                }
            )
    return tool_calls


def _build_run_diagnostics(
    *,
    request: AgentRunRequest,
    run_id: str,
    trace_id: str,
    status: str,
    started_at: datetime,
    finished_at: datetime | None = None,
    model_selected: str | None = None,
    token_usage: dict[str, int] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    assistant_message_count: int = 0,
    tool_message_count: int = 0,
    reasoning_chunk_count: int = 0,
    content_chunk_count: int = 0,
    output_characters: int = 0,
    output_preview: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    latency_ms = None
    if finished_at is not None:
        latency_ms = int((finished_at - started_at).total_seconds() * 1000)

    return {
        "run_id": run_id,
        "trace_id": trace_id,
        "name": "langgraph_agent_run",
        "run_type": "chain",
        "status": status,
        "application_id": request.application_id,
        "thread_id": request.thread_id,
        "profile_id": request.profile_id,
        "langsmith_project": settings.langsmith_project,
        "langsmith_endpoint": getenv("LANGSMITH_ENDPOINT"),
        "langsmith_tracing_enabled": settings.langsmith_tracing,
        "model_provider": "ollama",
        "model_primary": settings.ollama_primary_model,
        "model_fallbacks": [
            settings.ollama_fallback_cloud_model,
            settings.ollama_fallback_local_model,
        ],
        "model_selected": model_selected,
        "token_usage": token_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "tool_calls": tool_calls or [],
        "tool_call_count": len(tool_calls or []),
        "assistant_message_count": assistant_message_count,
        "tool_message_count": tool_message_count,
        "reasoning_chunk_count": reasoning_chunk_count,
        "content_chunk_count": content_chunk_count,
        "output_characters": output_characters,
        "input_preview": request.message[:240],
        "output_preview": output_preview[:240] if output_preview else None,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat() if finished_at is not None else None,
        "latency_ms": latency_ms,
        "error": error,
        "tags": ["langgraph", "streaming", "tui-compatible"],
    }


async def _invoke_agent(
    request: AgentRunRequest,
    *,
    run_id: str,
    trace_id: str,
    started_at: datetime,
) -> tuple[str, list[str], dict[str, Any]]:
    if state.agent_graph is None:
        message = "Agent graph not initialized"
        raise HTTPException(
            status_code=503,
            detail={
                "message": message,
                "run": _build_run_diagnostics(
                    request=request,
                    run_id=run_id,
                    trace_id=trace_id,
                    status="error",
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    error=message,
                ),
            },
        )

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
        message = f"Agent invocation failed: {exc}"
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "run": _build_run_diagnostics(
                    request=request,
                    run_id=run_id,
                    trace_id=trace_id,
                    status="error",
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    error=message,
                ),
            },
        ) from exc

    messages: list[BaseMessage] = result.get("messages", [])
    assistant_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
    tool_messages = [coerce_message_content(msg.content) for msg in messages if isinstance(msg, ToolMessage)]

    if not assistant_messages:
        message = "Agent response did not include an assistant message"
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "run": _build_run_diagnostics(
                    request=request,
                    run_id=run_id,
                    trace_id=trace_id,
                    status="error",
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    assistant_message_count=0,
                    tool_message_count=len(tool_messages),
                    error=message,
                ),
            },
        )

    final_message = assistant_messages[-1]
    answer_markdown = coerce_message_content(final_message.content)
    selected_model = _extract_model_name(final_message)
    if selected_model is None:
        for assistant_message in reversed(assistant_messages):
            selected_model = _extract_model_name(assistant_message)
            if selected_model:
                break

    run = _build_run_diagnostics(
        request=request,
        run_id=run_id,
        trace_id=trace_id,
        status="completed",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        model_selected=selected_model,
        token_usage=_extract_token_usage(assistant_messages),
        tool_calls=_extract_tool_calls(assistant_messages),
        assistant_message_count=len(assistant_messages),
        tool_message_count=len(tool_messages),
        output_characters=len(answer_markdown),
        output_preview=answer_markdown,
    )
    return answer_markdown, tool_messages, run


async def _agent_event_stream(request: AgentRunRequest) -> AsyncIterator[bytes]:
    run_id = f"run_{uuid4()}"
    trace_id = str(uuid4())
    started_at = datetime.now(UTC)

    initial_run = _build_run_diagnostics(
        request=request,
        run_id=run_id,
        trace_id=trace_id,
        status="running",
        started_at=started_at,
    )
    initial = _build_event(
        event_type="status",
        stream_state="queued",
        application_id=request.application_id,
        thread_id=request.thread_id,
        payload={"message": "agent_run_started", "run": initial_run},
    )
    yield f"{initial.model_dump_json()}\n".encode()

    try:
        answer_markdown, tool_messages, run = await _invoke_agent(
            request,
            run_id=run_id,
            trace_id=trace_id,
            started_at=started_at,
        )
    except HTTPException as exc:
        error_message = str(exc.detail)
        run_payload = _build_run_diagnostics(
            request=request,
            run_id=run_id,
            trace_id=trace_id,
            status="error",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error=error_message,
        )
        if isinstance(exc.detail, dict):
            error_message = str(exc.detail.get("message", error_message))
            detail_run = exc.detail.get("run")
            if isinstance(detail_run, dict):
                run_payload = detail_run

        error_event = _build_event(
            event_type="error",
            stream_state="error",
            application_id=request.application_id,
            thread_id=request.thread_id,
            payload={"message": error_message, "run": run_payload},
        )
        yield f"{error_event.model_dump_json()}\n".encode()
        return

    reasoning_chunk_count = 0
    for tool_message in tool_messages:
        for reasoning_chunk in _chunk_text(tool_message):
            reasoning_chunk_count += 1
            reasoning_event = _build_event(
                event_type="reasoning",
                stream_state="reasoning",
                application_id=request.application_id,
                thread_id=request.thread_id,
                payload={"delta": reasoning_chunk},
            )
            yield f"{reasoning_event.model_dump_json()}\n".encode()
            await asyncio.sleep(0)

    content_chunk_count = 0
    for content_chunk in _chunk_text(answer_markdown):
        content_chunk_count += 1
        content_event = _build_event(
            event_type="content",
            stream_state="generating",
            application_id=request.application_id,
            thread_id=request.thread_id,
            payload={"delta": content_chunk},
        )
        yield f"{content_event.model_dump_json()}\n".encode()
        await asyncio.sleep(0)

    run["reasoning_chunk_count"] = reasoning_chunk_count
    run["content_chunk_count"] = content_chunk_count
    run["output_characters"] = len(answer_markdown)

    completion = _build_event(
        event_type="complete",
        stream_state="completed",
        application_id=request.application_id,
        thread_id=request.thread_id,
        payload={"message": "completed", "run": run},
    )
    yield f"{completion.model_dump_json()}\n".encode()


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
    run_id = f"run_{uuid4()}"
    trace_id = str(uuid4())
    started_at = datetime.now(UTC)
    answer_markdown, tool_messages, run = await _invoke_agent(
        request,
        run_id=run_id,
        trace_id=trace_id,
        started_at=started_at,
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
        _agent_event_stream(request),
        media_type="application/x-ndjson",
    )
