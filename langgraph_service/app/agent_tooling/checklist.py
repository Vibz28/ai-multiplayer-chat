from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from langchain_core.tools import tool

ChecklistAction = Literal["replace", "add", "complete", "reopen", "remove", "list", "clear"]


@dataclass
class ChecklistItem:
    text: str
    done: bool = False


@dataclass
class ChecklistStore:
    _items_by_thread: dict[str, list[ChecklistItem]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def apply(
        self,
        *,
        thread_id: str,
        action: ChecklistAction,
        items: list[str] | None,
        indices: list[int] | None,
    ) -> str:
        normalized_thread_id = thread_id.strip() or "default"
        normalized_items = [item.strip() for item in (items or []) if item.strip()]
        normalized_indices = sorted({index for index in (indices or []) if index >= 1})

        with self._lock:
            checklist = self._items_by_thread.setdefault(normalized_thread_id, [])

            if action == "replace":
                checklist[:] = [ChecklistItem(text=item) for item in normalized_items]
            elif action == "add":
                checklist.extend(ChecklistItem(text=item) for item in normalized_items)
            elif action in {"complete", "reopen", "remove"}:
                if not normalized_indices:
                    return (
                        f"Checklist[{normalized_thread_id}] {action} requires one or more 1-based indices.\n"
                        f"Current checklist:\n{self._render(normalized_thread_id, checklist)}"
                    )

                if action == "remove":
                    for index in sorted(normalized_indices, reverse=True):
                        if 1 <= index <= len(checklist):
                            checklist.pop(index - 1)
                else:
                    target_done = action == "complete"
                    for index in normalized_indices:
                        if 1 <= index <= len(checklist):
                            checklist[index - 1].done = target_done
            elif action == "clear":
                checklist.clear()
            elif action == "list":
                pass

            if not checklist:
                self._items_by_thread.pop(normalized_thread_id, None)
                return f"Checklist[{normalized_thread_id}] is empty."

            return self._render(normalized_thread_id, checklist)

    def snapshot(self, thread_id: str) -> list[dict[str, object]]:
        normalized_thread_id = thread_id.strip() or "default"
        with self._lock:
            checklist = list(self._items_by_thread.get(normalized_thread_id, []))
        return [
            {"index": index, "text": item.text, "done": item.done}
            for index, item in enumerate(checklist, start=1)
        ]

    @staticmethod
    def _render(thread_id: str, checklist: list[ChecklistItem]) -> str:
        lines = [f"Checklist[{thread_id}]", "---"]
        for index, item in enumerate(checklist, start=1):
            marker = "x" if item.done else " "
            lines.append(f"{index}. [{marker}] {item.text}")
        return "\n".join(lines)


_CHECKLIST_STORE = ChecklistStore()


@tool
def manage_checklist(
    thread_id: str,
    action: ChecklistAction = "list",
    items: list[str] | None = None,
    indices: list[int] | None = None,
) -> str:
    """Manage a thread-scoped execution checklist for dynamic task tracking.

    Use this as a reusable agentic planning tool while solving user requests.

    Args:
        thread_id: Thread/session identifier that scopes checklist state.
        action: One of:
            - "replace": replace checklist with new items.
            - "add": append new items.
            - "complete": mark provided 1-based indices done.
            - "reopen": mark provided 1-based indices not done.
            - "remove": delete provided 1-based indices.
            - "list": show current checklist.
            - "clear": remove all checklist items.
        items: Checklist item text payload for replace/add actions.
        indices: 1-based checklist item indices for complete/reopen/remove actions.

    Returns:
        Rendered checklist text after applying the action.
    """

    return _CHECKLIST_STORE.apply(
        thread_id=thread_id,
        action=action,
        items=items,
        indices=indices,
    )


def get_checklist_items(thread_id: str) -> list[dict[str, object]]:
    """Return structured checklist items for API/diagnostic consumers."""
    return _CHECKLIST_STORE.snapshot(thread_id)
