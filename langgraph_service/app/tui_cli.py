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


def fetch_thread_history(base_url: str, thread_id: str, limit: int = 300) -> list[dict[str, Any]]:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(
            f"{base_url.rstrip('/')}/threads/{thread_id}/history",
            params={"limit": limit},
        )
        response.raise_for_status()
        payload = response.json()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


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
        self._panel_regions: dict[str, tuple[int, int, int, int]] = {}
        self._scrollbar_regions: dict[str, tuple[int, int, int, int]] = {}
        self._history_loaded = False

        self._colors_enabled = False
        self._color_pairs: dict[str, int] = {}

        # Prevent a large burst of events from being consumed in one frame.
        self._max_events_per_tick = 32

    def run(self) -> None:
        curses.wrapper(self._main)

    def _append_transcript(self, role: str, text: str, *, timestamp: str | None = None) -> None:
        timestamp = timestamp or datetime.now(UTC).strftime("%H:%M:%S")
        self._transcript_lines.append(f"[{timestamp}] {role}")
        cleaned = str(text).replace("\r", "")
        self._transcript_lines.extend(cleaned.split("\n") or [""])
        self._transcript_lines.append("")

    def _hydrate_from_history(self) -> None:
        if self._history_loaded or self.thread_id is None:
            return
        try:
            entries = fetch_thread_history(self.base_url, self.thread_id, limit=300)
        except Exception:
            return

        for entry in entries:
            channel = str(entry.get("channel", "transcript"))
            role = str(entry.get("role", "system"))
            content = str(entry.get("content", ""))
            created_at = str(entry.get("created_at", ""))
            run_id = entry.get("run_id")
            metadata = entry.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            ts = datetime.now(UTC).strftime("%H:%M:%S")
            if created_at:
                try:
                    ts = datetime.fromisoformat(created_at).strftime("%H:%M:%S")
                except ValueError:
                    ts = datetime.now(UTC).strftime("%H:%M:%S")

            if channel == "transcript":
                self._append_transcript(role, content, timestamp=ts)
                if role == "assistant":
                    label = run_id if isinstance(run_id, str) and run_id else "run-history"
                    self._output_history_lines.append(f"[{ts}] [{label}] {content}")
                continue

            if channel == "reasoning":
                label = run_id if isinstance(run_id, str) and run_id else "run-history"
                self._reasoning_history_lines.append(f"[{ts}] [{label}] {content}")
                continue

            if channel == "diagnostics":
                run_payload = metadata.get("run")
                if isinstance(run_payload, dict):
                    self._diagnostic_lines.append(f"[{created_at or ts}] run diagnostics")
                    self._diagnostic_lines.extend(format_run_diagnostics(run_payload))
                    self._diagnostic_lines.append("-" * 16)
                continue

            if channel == "error":
                self._append_transcript("error", content, timestamp=ts)

        self._history_loaded = True

    def _init_colors(self) -> None:
        if not curses.has_colors():
            return
        curses.start_color()
        curses.use_default_colors()
        # Core surface colors by panel.
        curses.init_pair(1, curses.COLOR_CYAN, -1)  # transcript
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # reasoning
        curses.init_pair(3, curses.COLOR_GREEN, -1)  # output
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)  # diagnostics
        curses.init_pair(5, curses.COLOR_BLUE, -1)  # events
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_CYAN)  # focused border/title
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_WHITE)  # status/input label
        curses.init_pair(8, curses.COLOR_WHITE, -1)  # help
        curses.init_pair(9, curses.COLOR_WHITE, -1)  # scrollbar track
        curses.init_pair(10, curses.COLOR_CYAN, -1)  # scrollbar thumb
        self._color_pairs = {
            self.PANEL_TRANSCRIPT: 1,
            self.PANEL_REASONING: 2,
            self.PANEL_OUTPUT: 3,
            self.PANEL_DIAGNOSTICS: 4,
            self.PANEL_EVENTS: 5,
            "focused": 6,
            "status": 7,
            "help": 8,
            "scroll_track": 9,
            "scroll_thumb": 10,
        }
        self._colors_enabled = True

    def _main(self, screen) -> None:
        curses.curs_set(1)
        screen.nodelay(True)
        screen.keypad(True)
        self._init_colors()
        curses.mouseinterval(0)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except curses.error:
            pass

        while self._running:
            self._drain_event_queue()
            self._render(screen)
            self._read_key(screen)
            time.sleep(0.03)

    def _focused_panel(self) -> str:
        return self._panel_order[self._panel_focus_index]

    def _color_attr(self, key: str, *, fallback: int = 0) -> int:
        if not self._colors_enabled:
            return fallback
        pair = self._color_pairs.get(key)
        if pair is None:
            return fallback
        return curses.color_pair(pair)

    def _cycle_focus(self, step: int) -> None:
        self._panel_focus_index = (self._panel_focus_index + step) % len(self._panel_order)

    def _set_focus_panel(self, panel_id: str) -> None:
        if panel_id in self._panel_order:
            self._panel_focus_index = self._panel_order.index(panel_id)

    def _panel_from_coords(self, y: int, x: int) -> str | None:
        for panel_id, (py, px, pheight, pwidth) in self._panel_regions.items():
            if py <= y < py + pheight and px <= x < px + pwidth:
                return panel_id
        return None

    def _is_scrollbar_click(self, panel_id: str, y: int, x: int) -> bool:
        region = self._scrollbar_regions.get(panel_id)
        if region is None:
            return False
        track_x, track_y_start, inner_height, _ = region
        return x == track_x and track_y_start <= y < track_y_start + inner_height

    def _scroll_to_track_position(self, panel_id: str, y: int) -> None:
        region = self._scrollbar_regions.get(panel_id)
        if region is None:
            return
        track_x, track_y_start, inner_height, max_offset = region
        del track_x
        if inner_height <= 0:
            return
        rel = min(max(0, y - track_y_start), inner_height - 1)
        if max_offset <= 0:
            self._scroll_offsets[panel_id] = 0
            return
        normalized = 1.0 - (rel / max(1, inner_height - 1))
        self._scroll_offsets[panel_id] = int(round(normalized * max_offset))

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

        if key == curses.KEY_MOUSE:
            try:
                _, mouse_x, mouse_y, _, button_state = curses.getmouse()
            except curses.error:
                return

            panel = self._panel_from_coords(mouse_y, mouse_x)
            if panel is not None:
                self._set_focus_panel(panel)

            left_click_mask = (
                getattr(curses, "BUTTON1_PRESSED", 0)
                | getattr(curses, "BUTTON1_CLICKED", 0)
                | getattr(curses, "BUTTON1_DOUBLE_CLICKED", 0)
                | getattr(curses, "BUTTON1_TRIPLE_CLICKED", 0)
            )
            wheel_up_mask = (
                getattr(curses, "BUTTON4_PRESSED", 0)
                | getattr(curses, "BUTTON4_CLICKED", 0)
                | getattr(curses, "BUTTON4_DOUBLE_CLICKED", 0)
                | getattr(curses, "BUTTON4_TRIPLE_CLICKED", 0)
            )
            wheel_down_mask = (
                getattr(curses, "BUTTON5_PRESSED", 0)
                | getattr(curses, "BUTTON5_CLICKED", 0)
                | getattr(curses, "BUTTON5_DOUBLE_CLICKED", 0)
                | getattr(curses, "BUTTON5_TRIPLE_CLICKED", 0)
            )

            if button_state & wheel_up_mask:
                self._scroll_focused(3)
                return

            if button_state & wheel_down_mask:
                self._scroll_focused(-3)
                return

            if panel is not None and button_state & left_click_mask and self._is_scrollbar_click(
                panel, mouse_y, mouse_x
            ):
                self._scroll_to_track_position(panel, mouse_y)
                return

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

        if key == 14:  # Ctrl+N inserts newline in prompt composer.
            self._input_buffer += "\n"
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
            self._hydrate_from_history()
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
        if lines:
            return lines
        if self._streaming:
            return ["(waiting for reasoning/tool events)"]
        return ["(no reasoning emitted by model/tools)"]

    def _output_panel_lines(self) -> list[str]:
        lines = list(self._output_history_lines)
        if self._active_output:
            label = self._active_run_id or "run-live"
            lines.append(f"[live {label}] {self._active_output}")
        if lines:
            return lines
        if self._streaming:
            return ["(waiting for content stream)"]
        return ["(no output yet)"]

    def _render(self, screen) -> None:
        screen.erase()
        height, width = screen.getmaxyx()

        composer_rows = 3
        input_height = 1 + 1 + composer_rows + 2
        main_height = max(8, height - input_height)
        left_width = max(45, int(width * 0.65))
        right_width = width - left_width

        left_transcript_height = max(5, int(main_height * 0.48))
        left_reasoning_height = max(4, int(main_height * 0.22))
        left_output_height = main_height - left_transcript_height - left_reasoning_height

        right_diag_height = max(5, int(main_height * 0.63))
        right_event_height = main_height - right_diag_height

        self._panel_regions.clear()
        self._scrollbar_regions.clear()

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

        prompt_lines = wrap_lines([self._input_buffer], width=max(1, width - 4))
        visible_prompt = prompt_lines[-composer_rows:] if prompt_lines else [""]
        if len(prompt_lines) > composer_rows and visible_prompt:
            visible_prompt[0] = f"...{visible_prompt[0]}"

        focused = self._focused_panel()
        status = (
            f"{self._status_line} | app={self.application_id} | thread={self.thread_id or '-'} | "
            f"profile={self.profile_id or '-'} | service={self.base_url} | focus={focused}"
        )
        status_row = main_height
        status_attr = self._color_attr("status")
        screen.addnstr(
            status_row,
            0,
            normalize_display_text(status).ljust(width),
            width - 1,
            status_attr,
        )

        input_label_row = status_row + 1
        input_label = "Input (Ctrl+N newline, Enter send):"
        screen.addnstr(
            input_label_row,
            0,
            normalize_display_text(input_label).ljust(width),
            width - 1,
            status_attr,
        )

        prompt_start_row = input_label_row + 1
        for idx, line in enumerate(visible_prompt[:composer_rows]):
            prefix = "> " if idx == 0 else "  "
            prompt_line = f"{prefix}{line}"
            screen.addnstr(
                prompt_start_row + idx,
                0,
                normalize_display_text(prompt_line).ljust(width),
                width - 1,
            )

        help_line_1 = "Navigation: Tab/Shift+Tab focus | Up/Down line scroll | PgUp/PgDn page scroll | Home/End jump"
        help_line_2 = "Mouse: click panel focus | click scrollbar for fine scroll | wheel scroll | /clear | /quit"
        help_attr = self._color_attr("help")
        screen.addnstr(
            height - 2,
            0,
            normalize_display_text(help_line_1).ljust(width),
            width - 1,
            help_attr,
        )
        screen.addnstr(
            height - 1,
            0,
            normalize_display_text(help_line_2).ljust(width),
            width - 1,
            help_attr,
        )

        # Place the cursor exactly where the user is typing.
        cursor_line = visible_prompt[-1] if visible_prompt else ""
        cursor_row = prompt_start_row + min(len(visible_prompt) - 1, composer_rows - 1)
        cursor_col = min(width - 1, 2 + len(normalize_display_text(cursor_line)))
        try:
            screen.move(cursor_row, cursor_col)
        except curses.error:
            pass

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

        self._panel_regions[panel_id] = (y, x, height, width)
        panel = screen.derwin(height, width, y, x)
        focused = panel_id == self._focused_panel()
        border_attr = self._color_attr("focused" if focused else panel_id)
        text_attr = self._color_attr(panel_id)
        track_attr = self._color_attr("scroll_track")
        thumb_attr = self._color_attr("scroll_thumb")
        if border_attr:
            panel.attron(border_attr)
        panel.box()
        if border_attr:
            panel.attroff(border_attr)

        inner_height = height - 2
        inner_width = width - 2
        scrollbar_enabled = inner_width >= 4
        text_width = inner_width - 1 if scrollbar_enabled else inner_width
        wrapped = wrap_lines(lines, text_width)
        visible, max_offset = viewport_slice(
            wrapped,
            inner_height=inner_height,
            offset=self._scroll_offsets.get(panel_id, 0),
        )

        self._panel_max_offsets[panel_id] = max_offset
        self._panel_page_sizes[panel_id] = max(1, inner_height - 1)
        self._scroll_offsets[panel_id] = min(self._scroll_offsets.get(panel_id, 0), max_offset)

        focus_marker = "*" if focused else " "
        offset = self._scroll_offsets.get(panel_id, 0)
        title_suffix = f" {offset}/{max_offset}" if max_offset > 0 else ""
        panel_title = normalize_display_text(f"{focus_marker}{title}{title_suffix}")
        panel.addnstr(
            0,
            2,
            panel_title[: max(1, width - 4)],
            max(1, width - 4),
            border_attr,
        )

        for row, text in enumerate(visible[:inner_height], start=1):
            safe_text = normalize_display_text(text)[:text_width]
            try:
                panel.addnstr(row, 1, safe_text.ljust(text_width), text_width, text_attr)
            except curses.error:
                continue

        if scrollbar_enabled:
            track_x = width - 2
            thumb_size = 1
            thumb_top = inner_height - 1
            if max_offset > 0:
                thumb_size = max(1, int((inner_height * inner_height) / max(1, len(wrapped))))
                thumb_size = min(thumb_size, inner_height)
                normalized = offset / max_offset
                thumb_top = int((inner_height - thumb_size) * (1 - normalized))
            self._scrollbar_regions[panel_id] = (x + track_x, y + 1, inner_height, max_offset)

            for row in range(inner_height):
                try:
                    panel.addch(row + 1, track_x, ord("|"), track_attr)
                except curses.error:
                    continue
            for row in range(thumb_size):
                try:
                    panel.addch(thumb_top + row + 1, track_x, ord("#"), thumb_attr)
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
