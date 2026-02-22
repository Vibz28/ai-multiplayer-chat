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
decode_alt_sequence = tui_module.decode_alt_sequence
move_cursor_line_left = tui_module.move_cursor_line_left
move_cursor_word_left = tui_module.move_cursor_word_left
move_cursor_word_right = tui_module.move_cursor_word_right
normalize_display_text = tui_module.normalize_display_text
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


def test_wrap_lines_sanitizes_multiline_and_control_chars() -> None:
    wrapped = wrap_lines(["line-1\nline\x00-2\tend"], width=40)
    assert len(wrapped) >= 2
    assert all("\n" not in line for line in wrapped)
    assert all("\x00" not in line for line in wrapped)


def test_normalize_display_text_ascii_sanitization() -> None:
    normalized = normalize_display_text("hello\tworld\nsnowman=\u2603")
    assert normalized == "hello world snowman=?"


def test_decode_alt_sequence_for_word_navigation() -> None:
    assert decode_alt_sequence([ord("b")]) == "word_left"
    assert decode_alt_sequence([ord("f")]) == "word_right"
    assert decode_alt_sequence([127]) == "delete_word_left"
    assert decode_alt_sequence([91, 49, 59, 51, 68]) == "word_left"
    assert decode_alt_sequence([91, 49, 59, 51, 67]) == "word_right"


def test_word_cursor_helpers_move_across_tokens() -> None:
    text = "alpha   beta gamma"
    assert move_cursor_word_left(text, len(text)) == 13
    assert move_cursor_word_left(text, 13) == 8
    assert move_cursor_word_right(text, 0) == 5
    assert move_cursor_word_right(text, 5) == 12


def test_line_cursor_helper_moves_to_line_start() -> None:
    text = "alpha beta\ngamma delta"
    assert move_cursor_line_left(text, len(text)) == len("alpha beta\n")
    assert move_cursor_line_left(text, len("alpha")) == 0


def test_input_wrapped_view_tracks_cursor_position(tmp_path) -> None:
    app = LangGraphTui(
        base_url="http://localhost:8080",
        application_id="cli-test",
        profile_id="cli-user",
        thread_id="thread-test",
        log_file=tmp_path / "events.jsonl",
    )
    app._input_buffer = "one two three four five six seven"
    app._input_cursor = len("one two three four")

    visible, cursor_row, cursor_col = app._input_wrapped_view(text_width=10, rows=3)
    assert len(visible) == 3
    assert 0 <= cursor_row < 3
    assert 0 <= cursor_col < 10


def test_input_delete_word_and_line_helpers(tmp_path) -> None:
    app = LangGraphTui(
        base_url="http://localhost:8080",
        application_id="cli-test",
        profile_id="cli-user",
        thread_id="thread-test",
        log_file=tmp_path / "events.jsonl",
    )
    app._input_buffer = "alpha beta\ngamma delta"
    app._input_cursor = len(app._input_buffer)

    app._delete_word_before_cursor()
    assert app._input_buffer == "alpha beta\ngamma "
    assert app._input_cursor == len("alpha beta\ngamma ")

    app._delete_line_before_cursor()
    assert app._input_buffer == "alpha beta\n"
    assert app._input_cursor == len("alpha beta\n")


def test_export_text_contains_panel_content(tmp_path) -> None:
    app = LangGraphTui(
        base_url="http://localhost:8080",
        application_id="cli-test",
        profile_id="cli-user",
        thread_id="thread-test",
        log_file=tmp_path / "events.jsonl",
    )
    app._append_transcript("user", "hello")
    snapshot = app._build_export_text("all")
    assert "## Transcript" in snapshot
    assert "hello" in snapshot


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


def test_tui_transcript_entries_are_separated(tmp_path) -> None:
    app = LangGraphTui(
        base_url="http://localhost:8080",
        application_id="cli-test",
        profile_id="cli-user",
        thread_id="thread-test",
        log_file=tmp_path / "events.jsonl",
    )

    app._append_transcript("user", "first line\nsecond line")
    app._append_transcript("assistant", "reply")

    assert app._transcript_lines[0].endswith(" user")
    assert app._transcript_lines[1] == "first line"
    assert app._transcript_lines[2] == "second line"
    assert app._transcript_lines[3] == ""
    assert any(line.endswith(" assistant") for line in app._transcript_lines)
