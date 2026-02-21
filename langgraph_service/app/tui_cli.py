from __future__ import annotations

import argparse
import curses
import json
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any
from uuid import uuid4

import httpx


def parse_stream_line(line: str) -> dict[str, Any]:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("Stream payload must be a JSON object")
    return payload


def format_run_diagnostics(run: dict[str, Any]) -> list[str]:
    token_usage = run.get("token_usage", {})
    if not isinstance(token_usage, dict):
        token_usage = {}

    tool_calls = run.get("tool_calls", [])
    tool_call_names: list[str] = []
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if isinstance(call, dict):
                tool_call_names.append(str(call.get("name", "unknown")))

    lines = [
        f"run_id: {run.get('run_id', '-')}",
        f"trace_id: {run.get('trace_id', '-')}",
        f"status: {run.get('status', '-')}",
        f"project: {run.get('langsmith_project', '-')}",
        f"endpoint: {run.get('langsmith_endpoint', '-')}",
        f"tracing: {run.get('langsmith_tracing_enabled', '-')}",
        f"app/thread: {run.get('application_id', '-')}/{run.get('thread_id', '-')}",
        f"profile: {run.get('profile_id', '-')}",
        f"model: {run.get('model_selected', '-')}",
        f"primary: {run.get('model_primary', '-')}",
        f"fallbacks: {', '.join(run.get('model_fallbacks', []))}",
        "tokens: "
        f"prompt={token_usage.get('prompt_tokens', 0)}, "
        f"completion={token_usage.get('completion_tokens', 0)}, "
        f"total={token_usage.get('total_tokens', 0)}",
        f"latency_ms: {run.get('latency_ms', '-')}",
        f"messages: assistant={run.get('assistant_message_count', 0)}, "
        f"tool={run.get('tool_message_count', 0)}",
        f"chunks: reasoning={run.get('reasoning_chunk_count', 0)}, "
        f"content={run.get('content_chunk_count', 0)}",
        f"output_chars: {run.get('output_characters', 0)}",
        f"tools_called ({run.get('tool_call_count', 0)}): {', '.join(tool_call_names) or '-'}",
        f"started_at: {run.get('started_at', '-')}",
        f"finished_at: {run.get('finished_at', '-')}",
        f"error: {run.get('error', '-')}",
    ]
    return lines


def normalize_display_text(value: str) -> str:
    ascii_text = value.encode("ascii", errors="replace").decode("ascii")
    return "".join(char if 32 <= ord(char) <= 126 else " " for char in ascii_text)


def wrap_lines(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        for logical_line in str(line).replace("\r", "").split("\n") or [""]:
            sanitized = normalize_display_text(logical_line.expandtabs(4))
            chunks = textwrap.wrap(
                sanitized,
                width=max(1, width),
                replace_whitespace=False,
                drop_whitespace=False,
            ) or [""]
            wrapped.extend(chunks)
    return wrapped


def viewport_slice(lines: list[str], inner_height: int, offset: int) -> tuple[list[str], int]:
    if inner_height <= 0:
        return [], 0
    max_offset = max(0, len(lines) - inner_height)
    clamped_offset = min(max(0, offset), max_offset)
    end = len(lines) - clamped_offset
    start = max(0, end - inner_height)
    return lines[start:end], max_offset


def ensure_thread(base_url: str, application_id: str) -> str:
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/threads",
            json={"application_id": application_id},
        )
        response.raise_for_status()
        payload = response.json()
    thread_id = payload.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise RuntimeError("LangGraph /threads response missing thread_id")
    return thread_id


def stream_agent_events(
    *,
    base_url: str,
    application_id: str,
    thread_id: str,
    profile_id: str | None,
    message: str,
):
    request_payload = {
        "application_id": application_id,
        "thread_id": thread_id,
        "profile_id": profile_id,
        "message": message,
    }
    with httpx.Client(timeout=None) as client:
        with client.stream(
            "POST",
            f"{base_url.rstrip('/')}/agent/stream",
            json=request_payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                yield parse_stream_line(line)


class LangGraphTui:
    PANEL_TRANSCRIPT = "transcript"
    PANEL_REASONING = "reasoning"
    PANEL_OUTPUT = "output"
    PANEL_DIAGNOSTICS = "diagnostics"
    PANEL_EVENTS = "events"

    def __init__(
        self,
        *,
        base_url: str,
        application_id: str,
        profile_id: str | None,
        thread_id: str | None,
        log_file: Path,
    ) -> None:
        self.base_url = base_url
        self.application_id = application_id
        self.profile_id = profile_id
        self.thread_id = thread_id
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self._event_queue: Queue[dict[str, Any]] = Queue()
        self._stream_thread: Thread | None = None
        self._running = True
        self._streaming = False

        self._input_buffer = ""
        self._status_line = "Type a prompt and press Enter. Use /quit to exit."

        self._transcript_lines: list[str] = []
        self._reasoning_history_lines: list[str] = []
        self._output_history_lines: list[str] = []
        self._active_reasoning = ""
        self._active_output = ""
        self._active_run_id: str | None = None

        self._diagnostic_lines: list[str] = []
        self._event_lines: list[str] = []

        self._panel_order = [
            self.PANEL_TRANSCRIPT,
            self.PANEL_REASONING,
            self.PANEL_OUTPUT,
            self.PANEL_DIAGNOSTICS,
            self.PANEL_EVENTS,
        ]
        self._panel_focus_index = 0
        self._scroll_offsets = {panel: 0 for panel in self._panel_order}
        self._panel_max_offsets = {panel: 0 for panel in self._panel_order}
        self._panel_page_sizes = {panel: 10 for panel in self._panel_order}

        # Prevent a large burst of events from being consumed in one frame.
        self._max_events_per_tick = 32

    def run(self) -> None:
        curses.wrapper(self._main)

    def _append_transcript(self, role: str, text: str) -> None:
        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        self._transcript_lines.append(f"[{timestamp}] {role}")
        cleaned = str(text).replace("\r", "")
        self._transcript_lines.extend(cleaned.split("\n") or [""])
        self._transcript_lines.append("")

    def _main(self, screen) -> None:
        curses.curs_set(1)
        screen.nodelay(True)
        screen.keypad(True)

        while self._running:
            self._drain_event_queue()
            self._render(screen)
            self._read_key(screen)
            time.sleep(0.03)

    def _focused_panel(self) -> str:
        return self._panel_order[self._panel_focus_index]

    def _cycle_focus(self, step: int) -> None:
        self._panel_focus_index = (self._panel_focus_index + step) % len(self._panel_order)

    def _scroll_focused(self, delta: int) -> None:
        panel = self._focused_panel()
        max_offset = self._panel_max_offsets.get(panel, 0)
        new_offset = self._scroll_offsets.get(panel, 0) + delta
        self._scroll_offsets[panel] = min(max(new_offset, 0), max_offset)

    def _jump_scroll(self, to_top: bool) -> None:
        panel = self._focused_panel()
        if to_top:
            self._scroll_offsets[panel] = self._panel_max_offsets.get(panel, 0)
        else:
            self._scroll_offsets[panel] = 0

    def _read_key(self, screen) -> None:
        key = screen.getch()
        if key == -1:
            return

        if key in (3,):  # Ctrl+C
            self._running = False
            return

        if key == 9:  # Tab
            self._cycle_focus(1)
            return

        if key == curses.KEY_BTAB:  # Shift+Tab
            self._cycle_focus(-1)
            return

        if key == curses.KEY_UP:
            self._scroll_focused(1)
            return

        if key == curses.KEY_DOWN:
            self._scroll_focused(-1)
            return

        if key == curses.KEY_PPAGE:
            self._scroll_focused(self._panel_page_sizes.get(self._focused_panel(), 10))
            return

        if key == curses.KEY_NPAGE:
            self._scroll_focused(-self._panel_page_sizes.get(self._focused_panel(), 10))
            return

        if key == curses.KEY_HOME:
            self._jump_scroll(to_top=True)
            return

        if key == curses.KEY_END:
            self._jump_scroll(to_top=False)
            return

        if key in (10, 13):  # Enter
            value = self._input_buffer.strip()
            self._input_buffer = ""
            if not value:
                return
            if value in {"/quit", "/exit"}:
                self._running = False
                return
            if value == "/clear":
                self._transcript_lines.clear()
                self._reasoning_history_lines.clear()
                self._output_history_lines.clear()
                self._active_reasoning = ""
                self._active_output = ""
                self._active_run_id = None
                self._diagnostic_lines.clear()
                self._event_lines.clear()
                self._status_line = "Cleared panes."
                for panel in self._panel_order:
                    self._scroll_offsets[panel] = 0
                return
            if self._streaming:
                self._status_line = "A run is already in progress. Wait for completion."
                return
            self._start_stream(value)
            return

        if key in (curses.KEY_BACKSPACE, 8, 127):
            self._input_buffer = self._input_buffer[:-1]
            return

        if 32 <= key <= 126:
            self._input_buffer += chr(key)

    def _start_stream(self, message: str) -> None:
        self._streaming = True
        self._active_reasoning = ""
        self._active_output = ""
        self._active_run_id = None
        self._status_line = "Streaming..."
        self._append_transcript("user", message)
        self._append_event("local", "queued", "user prompt submitted")
        self._scroll_offsets[self.PANEL_REASONING] = 0
        self._scroll_offsets[self.PANEL_OUTPUT] = 0

        self._stream_thread = Thread(
            target=self._stream_worker,
            args=(message,),
            daemon=True,
        )
        self._stream_thread.start()

    def _stream_worker(self, message: str) -> None:
        try:
            if self.thread_id is None:
                self.thread_id = ensure_thread(self.base_url, self.application_id)
                self._event_queue.put(
                    {
                        "type": "status",
                        "stream_state": "thread_ready",
                        "payload": {"message": f"thread resolved: {self.thread_id}"},
                    }
                )
            for event in stream_agent_events(
                base_url=self.base_url,
                application_id=self.application_id,
                thread_id=self.thread_id,
                profile_id=self.profile_id,
                message=message,
            ):
                self._event_queue.put(event)
        except Exception as exc:  # pragma: no cover - curses runtime surface
            self._event_queue.put(
                {
                    "type": "error",
                    "stream_state": "error",
                    "payload": {"message": f"stream failed: {exc}"},
                }
            )

    def _drain_event_queue(self) -> None:
        for _ in range(self._max_events_per_tick):
            try:
                event = self._event_queue.get_nowait()
            except Empty:
                return
            self._handle_event(event)

    def _finalize_active_buffers(self, *, add_to_transcript: bool) -> None:
        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        run_label = self._active_run_id or "run-unknown"

        if self._active_reasoning.strip():
            self._reasoning_history_lines.append(
                f"[{timestamp}] [{run_label}] {self._active_reasoning}"
            )
        if self._active_output.strip():
            self._output_history_lines.append(f"[{timestamp}] [{run_label}] {self._active_output}")
            if add_to_transcript:
                self._append_transcript("assistant", self._active_output)

        self._active_reasoning = ""
        self._active_output = ""

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", "status"))
        stream_state = str(event.get("stream_state", "unknown"))
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"value": payload}

        delta = payload.get("delta")
        message = payload.get("message")
        run = payload.get("run")

        if isinstance(run, dict):
            run_id = run.get("run_id")
            if isinstance(run_id, str) and run_id:
                self._active_run_id = run_id

            timestamp = datetime.now(UTC).isoformat()
            self._diagnostic_lines.append(f"[{timestamp}] run diagnostics")
            self._diagnostic_lines.extend(format_run_diagnostics(run))
            self._diagnostic_lines.append("-" * 16)
            self._write_log({"kind": "run", "captured_at": timestamp, "run": run})
            if self._scroll_offsets[self.PANEL_DIAGNOSTICS] == 0:
                self._scroll_offsets[self.PANEL_DIAGNOSTICS] = 0

        if event_type == "reasoning" and isinstance(delta, str):
            self._active_reasoning += delta
        elif event_type == "content" and isinstance(delta, str):
            self._active_output += delta
        elif event_type == "complete":
            self._streaming = False
            self._status_line = "Completed."
            self._finalize_active_buffers(add_to_transcript=True)
        elif event_type == "error":
            self._streaming = False
            self._status_line = "Error."
            self._finalize_active_buffers(add_to_transcript=False)
            self._append_transcript("error", str(payload.get("message", "unknown error")))

        event_message = str(message or delta or "")
        self._append_event(event_type, stream_state, event_message[:120])

        self._write_log(
            {
                "kind": "event",
                "captured_at": datetime.now(UTC).isoformat(),
                "event": event,
            }
        )

    def _append_event(self, event_type: str, stream_state: str, content: str) -> None:
        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        self._event_lines.append(f"[{timestamp}] {event_type}/{stream_state} {content}")

    def _write_log(self, payload: dict[str, Any]) -> None:
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def _reasoning_panel_lines(self) -> list[str]:
        lines = list(self._reasoning_history_lines)
        if self._active_reasoning:
            label = self._active_run_id or "run-live"
            lines.append(f"[live {label}] {self._active_reasoning}")
        return lines or ["(waiting)"]

    def _output_panel_lines(self) -> list[str]:
        lines = list(self._output_history_lines)
        if self._active_output:
            label = self._active_run_id or "run-live"
            lines.append(f"[live {label}] {self._active_output}")
        return lines or ["(waiting)"]

    def _render(self, screen) -> None:
        screen.erase()
        height, width = screen.getmaxyx()

        input_height = 3
        main_height = max(8, height - input_height)
        left_width = max(45, int(width * 0.65))
        right_width = width - left_width

        left_transcript_height = max(5, int(main_height * 0.48))
        left_reasoning_height = max(4, int(main_height * 0.22))
        left_output_height = main_height - left_transcript_height - left_reasoning_height

        right_diag_height = max(5, int(main_height * 0.63))
        right_event_height = main_height - right_diag_height

        self._draw_panel(
            screen,
            panel_id=self.PANEL_TRANSCRIPT,
            y=0,
            x=0,
            height=left_transcript_height,
            width=left_width,
            title="Transcript",
            lines=self._transcript_lines,
        )
        self._draw_panel(
            screen,
            panel_id=self.PANEL_REASONING,
            y=left_transcript_height,
            x=0,
            height=left_reasoning_height,
            width=left_width,
            title="Reasoning Stream",
            lines=self._reasoning_panel_lines(),
        )
        self._draw_panel(
            screen,
            panel_id=self.PANEL_OUTPUT,
            y=left_transcript_height + left_reasoning_height,
            x=0,
            height=left_output_height,
            width=left_width,
            title="Output Stream",
            lines=self._output_panel_lines(),
        )
        self._draw_panel(
            screen,
            panel_id=self.PANEL_DIAGNOSTICS,
            y=0,
            x=left_width,
            height=right_diag_height,
            width=right_width,
            title="LangSmith-Style Diagnostics",
            lines=self._diagnostic_lines,
        )
        self._draw_panel(
            screen,
            panel_id=self.PANEL_EVENTS,
            y=right_diag_height,
            x=left_width,
            height=right_event_height,
            width=right_width,
            title="Event Log",
            lines=self._event_lines,
        )

        focused = self._focused_panel()
        status = (
            f"{self._status_line} | app={self.application_id} | thread={self.thread_id or '-'} | "
            f"profile={self.profile_id or '-'} | service={self.base_url} | focus={focused}"
        )
        screen.addnstr(height - 3, 0, status.ljust(width), width - 1)
        prompt = f"> {self._input_buffer}"
        screen.addnstr(height - 2, 0, prompt.ljust(width), width - 1)
        screen.addnstr(
            height - 1,
            0,
            "Enter=send Tab=next Shift+Tab=prev Up/Down PgUp/PgDn Home/End=scroll /clear /quit".ljust(width),
            width - 1,
        )
        screen.refresh()

    def _draw_panel(
        self,
        screen,
        *,
        panel_id: str,
        y: int,
        x: int,
        height: int,
        width: int,
        title: str,
        lines: list[str],
    ) -> None:
        if height < 3 or width < 8:
            return

        panel = screen.derwin(height, width, y, x)
        panel.box()

        inner_height = height - 2
        inner_width = width - 2
        wrapped = wrap_lines(lines, inner_width)
        visible, max_offset = viewport_slice(
            wrapped,
            inner_height=inner_height,
            offset=self._scroll_offsets.get(panel_id, 0),
        )

        self._panel_max_offsets[panel_id] = max_offset
        self._panel_page_sizes[panel_id] = max(1, inner_height - 1)
        self._scroll_offsets[panel_id] = min(self._scroll_offsets.get(panel_id, 0), max_offset)

        focus_marker = "*" if panel_id == self._focused_panel() else " "
        offset = self._scroll_offsets.get(panel_id, 0)
        title_suffix = f" {offset}/{max_offset}" if max_offset > 0 else ""
        panel_title = normalize_display_text(f"{focus_marker}{title}{title_suffix}")
        panel.addnstr(0, 2, panel_title[: max(1, width - 4)], max(1, width - 4))

        for row, text in enumerate(visible[:inner_height], start=1):
            safe_text = normalize_display_text(text)[:inner_width]
            try:
                panel.addnstr(row, 1, safe_text.ljust(inner_width), inner_width)
            except curses.error:
                continue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive TUI client for LangGraph streaming with diagnostics.",
    )
    parser.add_argument(
        "--langgraph-url",
        default="http://localhost:8080",
        help="LangGraph service base URL.",
    )
    parser.add_argument(
        "--application-id",
        default=f"cli-{uuid4().hex[:8]}",
        help="Application ID used to resolve or create a thread.",
    )
    parser.add_argument(
        "--profile-id",
        default="cli-user",
        help="Profile identifier sent to the LangGraph run.",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional existing thread ID. If omitted, the tool resolves one via /threads.",
    )
    parser.add_argument(
        "--log-file",
        default="logs/langgraph_tui_events.jsonl",
        help="Path for JSONL event/run logs.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = LangGraphTui(
        base_url=args.langgraph_url,
        application_id=args.application_id,
        profile_id=args.profile_id,
        thread_id=args.thread_id,
        log_file=Path(args.log_file),
    )
    app.run()


if __name__ == "__main__":
    main()
