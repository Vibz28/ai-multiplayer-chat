from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

service_root = Path(__file__).resolve().parents[2]

tui_spec = spec_from_file_location("langgraph_service_tui_cli", service_root / "app" / "tui_cli.py")
if tui_spec is None or tui_spec.loader is None:
    raise RuntimeError("Unable to load langgraph_service tui module")
tui_module = module_from_spec(tui_spec)
tui_spec.loader.exec_module(tui_module)

format_run_diagnostics = tui_module.format_run_diagnostics
LangGraphTui = tui_module.LangGraphTui
parse_stream_line = tui_module.parse_stream_line
viewport_slice = tui_module.viewport_slice
wrap_lines = tui_module.wrap_lines


def test_parse_stream_line_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_stream_line('["not-an-object"]')


def test_parse_stream_line_accepts_object_payload() -> None:
    payload = parse_stream_line('{"type":"content","payload":{"delta":"hello"}}')
    assert payload["type"] == "content"
    assert payload["payload"]["delta"] == "hello"


def test_format_run_diagnostics_exposes_langsmith_style_fields() -> None:
    diagnostics = format_run_diagnostics(
        {
            "run_id": "run-123",
            "trace_id": "trace-123",
            "status": "completed",
            "langsmith_project": "ai-multiplayer-chat",
            "langsmith_endpoint": "https://api.smith.langchain.com",
            "langsmith_tracing_enabled": True,
            "application_id": "app-1",
            "thread_id": "thread-1",
            "profile_id": "profile-1",
            "model_selected": "kimi-k2.5:cloud",
            "model_primary": "kimi-k2.5:cloud",
            "model_fallbacks": ["qwen3-vl:235b-cloud", "gpt-oss:20b"],
            "token_usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30},
            "latency_ms": 421,
            "assistant_message_count": 2,
            "tool_message_count": 1,
            "reasoning_chunk_count": 2,
            "content_chunk_count": 3,
            "output_characters": 256,
            "tool_call_count": 1,
            "tool_calls": [{"name": "describe_session_context"}],
            "started_at": "2026-02-21T00:00:00+00:00",
            "finished_at": "2026-02-21T00:00:01+00:00",
            "error": None,
        }
    )

    assert any("run_id: run-123" in line for line in diagnostics)
    assert any("trace_id: trace-123" in line for line in diagnostics)
    assert any("tokens: prompt=12, completion=18, total=30" in line for line in diagnostics)
    assert any("tools_called (1): describe_session_context" in line for line in diagnostics)


def test_wrap_lines_and_viewport_slice_support_scrollback() -> None:
    wrapped = wrap_lines(
        [
            "alpha",
            "beta gamma delta epsilon",
            "zeta",
        ],
        width=8,
    )

    latest, max_offset = viewport_slice(wrapped, inner_height=3, offset=0)
    older, _ = viewport_slice(wrapped, inner_height=3, offset=max_offset)

    assert max_offset >= 1
    assert latest[-1].strip() == "zeta"
    assert older[0].strip().startswith("alpha")


def test_tui_preserves_stream_output_after_completion(tmp_path) -> None:
    app = LangGraphTui(
        base_url="http://localhost:8080",
        application_id="cli-test",
        profile_id="cli-user",
        thread_id="thread-test",
        log_file=tmp_path / "events.jsonl",
    )
    app._streaming = True

    running_run = {"run_id": "run-1", "status": "running"}
    complete_run = {"run_id": "run-1", "status": "completed"}

    app._handle_event(
        {
            "type": "status",
            "stream_state": "queued",
            "payload": {"message": "started", "run": running_run},
        }
    )
    app._handle_event(
        {
            "type": "content",
            "stream_state": "generating",
            "payload": {"delta": "hello world"},
        }
    )
    assert "hello world" in app._output_panel_lines()[-1]

    app._handle_event(
        {
            "type": "complete",
            "stream_state": "completed",
            "payload": {"message": "completed", "run": complete_run},
        }
    )

    assert app._streaming is False
    assert app._active_output == ""
    assert any("hello world" in line for line in app._output_history_lines)
    assert any("hello world" in line for line in app._transcript_lines)
