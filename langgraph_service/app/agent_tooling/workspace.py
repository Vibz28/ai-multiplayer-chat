from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool

WORKSPACE_ROOT = Path(os.environ.get("LANGGRAPH_WORKSPACE_ROOT", "/workspace")).resolve()
MAX_READ_BYTES = 200_000
MAX_WRITE_BYTES = 500_000


def resolve_workspace_path(relative_path: str) -> Path:
    candidate = (WORKSPACE_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(WORKSPACE_ROOT)
    except ValueError as error:
        raise ValueError("path must stay inside the worker workspace") from error
    return candidate


@tool
def list_workspace(relative_path: str = ".") -> str:
    """List files and directories inside the isolated worker workspace."""
    directory = resolve_workspace_path(relative_path)
    if not directory.exists():
        return "Path does not exist."
    if not directory.is_dir():
        return f"{relative_path} is a file."

    entries: list[str] = []
    for item in sorted(directory.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower())):
        kind = "directory" if item.is_dir() else "file"
        size = "" if item.is_dir() else f" ({item.stat().st_size} bytes)"
        entries.append(f"- {item.name} [{kind}]{size}")
        if len(entries) >= 200:
            entries.append("- ... list limited to 200 entries")
            break
    return "\n".join(entries) if entries else "Workspace is empty."


@tool
def read_workspace_file(relative_path: str) -> str:
    """Read one UTF-8 text file from the isolated worker workspace."""
    target = resolve_workspace_path(relative_path)
    if not target.is_file():
        raise ValueError("requested workspace path is not a file")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"file exceeds the {MAX_READ_BYTES}-byte read limit")
    return target.read_text(encoding="utf-8")


@tool
def write_workspace_file(relative_path: str, content: str) -> str:
    """Create or replace one UTF-8 deliverable file inside the isolated worker workspace."""
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        raise ValueError(f"content exceeds the {MAX_WRITE_BYTES}-byte write limit")

    target = resolve_workspace_path(relative_path)
    if target == WORKSPACE_ROOT:
        raise ValueError("a file path is required")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(target)
    return f"Saved {target.relative_to(WORKSPACE_ROOT)} ({len(encoded)} bytes)."
