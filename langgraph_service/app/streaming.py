from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.agent import coerce_message_content
from app.agent_tooling import get_checklist_items
from app.diagnostics import (
    build_event,
    build_run_diagnostics,
    chunk_text,
    extract_model_name,
    extract_token_usage,
    extract_tool_calls,
)
from app.history_store import persist_history_entry
from app.runtime import state
from app.schemas import AgentRunRequest


def _graph_payload(request: AgentRunRequest) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": request.message}],
        "user_message": request.message,
        "application_id": request.application_id,
        "thread_id": request.thread_id,
        "profile_id": request.profile_id,
    }


def _graph_config(request: AgentRunRequest) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": request.thread_id,
            "application_id": request.application_id,
            "profile_id": request.profile_id,
        }
    }


async def invoke_agent(
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
                "run": build_run_diagnostics(
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
            _graph_payload(request),
            config=_graph_config(request),
        )
    except Exception as exc:
        message = f"Agent invocation failed: {exc}"
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "run": build_run_diagnostics(
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
                "run": build_run_diagnostics(
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
    selected_model = extract_model_name(final_message)
    if selected_model is None:
        for assistant_message in reversed(assistant_messages):
            selected_model = extract_model_name(assistant_message)
            if selected_model:
                break

    run = build_run_diagnostics(
        request=request,
        run_id=run_id,
        trace_id=trace_id,
        status="completed",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        model_selected=selected_model,
        token_usage=extract_token_usage(assistant_messages),
        tool_calls=extract_tool_calls(assistant_messages),
        assistant_message_count=len(assistant_messages),
        tool_message_count=len(tool_messages),
        output_characters=len(answer_markdown),
        output_preview=answer_markdown,
    )

    return answer_markdown, tool_messages, run


async def agent_event_stream(request: AgentRunRequest) -> AsyncIterator[bytes]:
    run_id = f"run_{uuid4()}"
    trace_id = str(uuid4())
    started_at = datetime.now(UTC)

    initial_run = build_run_diagnostics(
        request=request,
        run_id=run_id,
        trace_id=trace_id,
        status="running",
        started_at=started_at,
    )
    initial = build_event(
        event_type="status",
        stream_state="queued",
        application_id=request.application_id,
        thread_id=request.thread_id,
        payload={"message": "agent_run_started", "run": initial_run},
    )
    yield f"{initial.model_dump_json()}\n".encode()

    checklist_signature = ""

    def build_checklist_event(stream_state: str) -> bytes | None:
        nonlocal checklist_signature
        items = get_checklist_items(request.thread_id)
        serialized = json.dumps(items, sort_keys=True, separators=(",", ":"))
        if serialized == checklist_signature:
            return None
        checklist_signature = serialized
        checklist_event = build_event(
            event_type="checklist",
            stream_state=stream_state,
            application_id=request.application_id,
            thread_id=request.thread_id,
            payload={"items": items, "count": len(items)},
        )
        return f"{checklist_event.model_dump_json()}\n".encode()

    initial_checklist = build_checklist_event("queued")
    if initial_checklist is not None:
        yield initial_checklist

    await persist_history_entry(
        application_id=request.application_id,
        thread_id=request.thread_id,
        profile_id=request.profile_id,
        role="user",
        channel="transcript",
        content=request.message,
        run_id=run_id,
        trace_id=trace_id,
        metadata={"source": "agent_stream"},
    )

    if state.agent_graph is None:
        message = "Agent graph not initialized"
        run = build_run_diagnostics(
            request=request,
            run_id=run_id,
            trace_id=trace_id,
            status="error",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error=message,
        )
        error_event = build_event(
            event_type="error",
            stream_state="error",
            application_id=request.application_id,
            thread_id=request.thread_id,
            payload={"message": message, "run": run},
        )
        yield f"{error_event.model_dump_json()}\n".encode()
        await persist_history_entry(
            application_id=request.application_id,
            thread_id=request.thread_id,
            profile_id=request.profile_id,
            role="system",
            channel="error",
            content=message,
            run_id=run_id,
            trace_id=trace_id,
            metadata={"run": run},
        )
        return

    assistant_messages: list[AIMessage] = []
    tool_messages: list[str] = []
    answer_parts: list[str] = []
    reasoning_chunk_count = 0
    content_chunk_count = 0

    try:
        async for stream_event in state.agent_graph.astream_events(
            _graph_payload(request),
            config=_graph_config(request),
            version="v2",
        ):
            event_name = str(stream_event.get("event", ""))
            payload = stream_event.get("data", {})
            if not isinstance(payload, dict):
                continue

            if event_name == "on_tool_end":
                raw_output = payload.get("output")
                reasoning_text = coerce_message_content(getattr(raw_output, "content", raw_output))
                if not reasoning_text:
                    continue
                tool_messages.append(reasoning_text)
                for reasoning_chunk in chunk_text(reasoning_text):
                    reasoning_chunk_count += 1
                    reasoning_event = build_event(
                        event_type="reasoning",
                        stream_state="reasoning",
                        application_id=request.application_id,
                        thread_id=request.thread_id,
                        payload={"delta": reasoning_chunk},
                    )
                    yield f"{reasoning_event.model_dump_json()}\n".encode()
                checklist_event = build_checklist_event("reasoning")
                if checklist_event is not None:
                    yield checklist_event
                continue

            if event_name == "on_chat_model_stream":
                chunk = payload.get("chunk")
                if chunk is None:
                    continue
                delta = coerce_message_content(getattr(chunk, "content", chunk))
                if not delta:
                    continue
                answer_parts.append(delta)
                content_chunk_count += 1
                content_event = build_event(
                    event_type="content",
                    stream_state="generating",
                    application_id=request.application_id,
                    thread_id=request.thread_id,
                    payload={"delta": delta},
                )
                yield f"{content_event.model_dump_json()}\n".encode()
                continue

            if event_name == "on_chat_model_end":
                output = payload.get("output")
                if isinstance(output, AIMessage):
                    assistant_messages.append(output)
                elif isinstance(output, dict):
                    candidate = output.get("message") or output.get("output")
                    if isinstance(candidate, AIMessage):
                        assistant_messages.append(candidate)
    except Exception as exc:
        message = f"Agent stream failed: {exc}"
        run = build_run_diagnostics(
            request=request,
            run_id=run_id,
            trace_id=trace_id,
            status="error",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            assistant_message_count=len(assistant_messages),
            tool_message_count=len(tool_messages),
            reasoning_chunk_count=reasoning_chunk_count,
            content_chunk_count=content_chunk_count,
            output_characters=len("".join(answer_parts)),
            output_preview="".join(answer_parts),
            error=message,
        )
        error_event = build_event(
            event_type="error",
            stream_state="error",
            application_id=request.application_id,
            thread_id=request.thread_id,
            payload={"message": message, "run": run},
        )
        yield f"{error_event.model_dump_json()}\n".encode()
        await persist_history_entry(
            application_id=request.application_id,
            thread_id=request.thread_id,
            profile_id=request.profile_id,
            role="system",
            channel="error",
            content=message,
            run_id=run_id,
            trace_id=trace_id,
            metadata={"run": run},
        )
        return

    answer_markdown = "".join(answer_parts)

    if not answer_markdown and assistant_messages:
        answer_markdown = coerce_message_content(assistant_messages[-1].content)
        if answer_markdown:
            content_chunk_count += 1
            content_event = build_event(
                event_type="content",
                stream_state="generating",
                application_id=request.application_id,
                thread_id=request.thread_id,
                payload={"delta": answer_markdown},
            )
            yield f"{content_event.model_dump_json()}\n".encode()

    if not assistant_messages and not answer_markdown:
        try:
            fallback_answer, fallback_tool_messages, fallback_run = await invoke_agent(
                request,
                run_id=run_id,
                trace_id=trace_id,
                started_at=started_at,
            )
        except HTTPException as exc:
            error_message = str(exc.detail)
            fallback_error_run = build_run_diagnostics(
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
                    fallback_error_run = detail_run

            error_event = build_event(
                event_type="error",
                stream_state="error",
                application_id=request.application_id,
                thread_id=request.thread_id,
                payload={"message": error_message, "run": fallback_error_run},
            )
            yield f"{error_event.model_dump_json()}\n".encode()
            await persist_history_entry(
                application_id=request.application_id,
                thread_id=request.thread_id,
                profile_id=request.profile_id,
                role="system",
                channel="error",
                content=error_message,
                run_id=run_id,
                trace_id=trace_id,
                metadata={"run": fallback_error_run},
            )
            return

        for tool_message in fallback_tool_messages:
            for reasoning_chunk in chunk_text(tool_message):
                reasoning_chunk_count += 1
                reasoning_event = build_event(
                    event_type="reasoning",
                    stream_state="reasoning",
                    application_id=request.application_id,
                    thread_id=request.thread_id,
                    payload={"delta": reasoning_chunk},
                )
                yield f"{reasoning_event.model_dump_json()}\n".encode()
            checklist_event = build_checklist_event("reasoning")
            if checklist_event is not None:
                yield checklist_event

        if fallback_answer:
            for content_chunk in chunk_text(fallback_answer):
                content_chunk_count += 1
                content_event = build_event(
                    event_type="content",
                    stream_state="generating",
                    application_id=request.application_id,
                    thread_id=request.thread_id,
                    payload={"delta": content_chunk},
                )
                yield f"{content_event.model_dump_json()}\n".encode()

        fallback_run["reasoning_chunk_count"] = reasoning_chunk_count
        fallback_run["content_chunk_count"] = content_chunk_count
        fallback_run["output_characters"] = len(fallback_answer)

        checklist_event = build_checklist_event("completed")
        if checklist_event is not None:
            yield checklist_event

        completion = build_event(
            event_type="complete",
            stream_state="completed",
            application_id=request.application_id,
            thread_id=request.thread_id,
            payload={"message": "completed", "run": fallback_run},
        )
        yield f"{completion.model_dump_json()}\n".encode()

        await persist_history_entry(
            application_id=request.application_id,
            thread_id=request.thread_id,
            profile_id=request.profile_id,
            role="assistant",
            channel="transcript",
            content=fallback_answer,
            run_id=run_id,
            trace_id=trace_id,
            metadata={"streamed": True},
        )
        if fallback_tool_messages:
            await persist_history_entry(
                application_id=request.application_id,
                thread_id=request.thread_id,
                profile_id=request.profile_id,
                role="assistant",
                channel="reasoning",
                content="\n\n".join(fallback_tool_messages),
                run_id=run_id,
                trace_id=trace_id,
                metadata={"streamed": True},
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
            metadata={"run": fallback_run},
        )
        return

    selected_model = None
    for assistant_message in reversed(assistant_messages):
        selected_model = extract_model_name(assistant_message)
        if selected_model:
            break

    run = build_run_diagnostics(
        request=request,
        run_id=run_id,
        trace_id=trace_id,
        status="completed",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        model_selected=selected_model,
        token_usage=extract_token_usage(assistant_messages),
        tool_calls=extract_tool_calls(assistant_messages),
        assistant_message_count=len(assistant_messages),
        tool_message_count=len(tool_messages),
        reasoning_chunk_count=reasoning_chunk_count,
        content_chunk_count=content_chunk_count,
        output_characters=len(answer_markdown),
        output_preview=answer_markdown,
    )

    completion = build_event(
        event_type="complete",
        stream_state="completed",
        application_id=request.application_id,
        thread_id=request.thread_id,
        payload={"message": "completed", "run": run},
    )
    checklist_event = build_checklist_event("completed")
    if checklist_event is not None:
        yield checklist_event
    yield f"{completion.model_dump_json()}\n".encode()

    await persist_history_entry(
        application_id=request.application_id,
        thread_id=request.thread_id,
        profile_id=request.profile_id,
        role="assistant",
        channel="transcript",
        content=answer_markdown,
        run_id=run_id,
        trace_id=trace_id,
        metadata={"streamed": True},
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
            metadata={"streamed": True},
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
