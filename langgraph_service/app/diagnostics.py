from __future__ import annotations

from datetime import UTC, datetime
from os import getenv
from typing import Any

from langchain_core.messages import AIMessage

from app.runtime import settings
from app.schemas import AgentRunRequest, AgentStreamEvent


def build_event(
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


def chunk_text(text: str, chunk_size: int = 48) -> list[str]:
    return [text[idx : idx + chunk_size] for idx in range(0, len(text), chunk_size)]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def extract_model_name(message: AIMessage) -> str | None:
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


def extract_token_usage(assistant_messages: list[AIMessage]) -> dict[str, int]:
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


def extract_tool_calls(assistant_messages: list[AIMessage]) -> list[dict[str, Any]]:
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


def build_run_diagnostics(
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
