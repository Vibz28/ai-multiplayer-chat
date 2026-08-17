from __future__ import annotations

import json
from typing import Literal

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.config import get_settings


def _workspace_id(config: RunnableConfig) -> str:
    configurable = config.get("configurable", {})
    application_id = str(configurable.get("application_id", "")).strip()
    if not application_id:
        raise ValueError("worker workspace context is unavailable")
    return application_id


def _post(path: str, payload: dict[str, object], *, timeout: float = 310) -> str:
    response = httpx.post(
        f"{get_settings().worker_runtime_url.rstrip('/')}{path}",
        json=payload,
        headers={"X-Fieldwork-Runtime-Token": get_settings().runtime_token},
        timeout=timeout,
    )
    if response.is_error:
        try:
            detail = response.json().get("detail", "worker operation failed")
        except (ValueError, AttributeError):
            detail = "worker operation failed"
        return json.dumps(
            {"ok": False, "status_code": response.status_code, "error": detail},
            ensure_ascii=True,
        )
    return json.dumps(response.json(), ensure_ascii=True)


@tool
def workspace_search(
    mode: Literal["paths", "text"],
    config: RunnableConfig,
    path: str = ".",
    glob: str = "**/*",
    query: str | None = None,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> str:
    """Find paths or literal text inside this assignment's isolated workspace."""
    return _post(
        "/v1/tools/search",
        {
            "workspace_id": _workspace_id(config),
            "mode": mode,
            "path": path,
            "glob": glob,
            "query": query,
            "case_sensitive": case_sensitive,
            "max_results": max_results,
        },
    )


@tool
def workspace_read(
    path: str,
    config: RunnableConfig,
    start_line: int = 1,
    max_lines: int = 400,
) -> str:
    """Read a bounded range of lines and current hash from a workspace text file."""
    return _post(
        "/v1/tools/read",
        {
            "workspace_id": _workspace_id(config),
            "path": path,
            "start_line": start_line,
            "max_lines": max_lines,
        },
    )


@tool
def workspace_edit(
    path: str,
    operation: Literal["create", "replace", "overwrite", "delete"],
    config: RunnableConfig,
    expected_sha256: str | None = None,
    content: str | None = None,
    old_text: str | None = None,
    new_text: str | None = None,
) -> str:
    """Edit a file. Create needs content/new path; all other operations need the hash from workspace_read. Replace also needs old_text exactly once and new_text."""
    return _post(
        "/v1/tools/edit",
        {
            "workspace_id": _workspace_id(config),
            "path": path,
            "operation": operation,
            "expected_sha256": expected_sha256,
            "content": content,
            "old_text": old_text,
            "new_text": new_text,
        },
    )


@tool
def workspace_exec(
    argv: list[str],
    config: RunnableConfig,
    cwd: str = ".",
    timeout_seconds: int = 60,
    max_output_bytes: int = 100_000,
) -> str:
    """Run one argv-only command in the sandbox to inspect, build, or test workspace work."""
    return _post(
        "/v1/tools/exec",
        {
            "workspace_id": _workspace_id(config),
            "argv": argv,
            "cwd": cwd,
            "timeout_seconds": timeout_seconds,
            "max_output_bytes": max_output_bytes,
        },
        timeout=timeout_seconds + 10,
    )


@tool
def fetch_web(url: str, max_bytes: int = 200_000) -> str:
    """Fetch bounded text from a public HTTP or HTTPS URL; private network URLs are rejected."""
    return _post("/v1/tools/fetch", {"url": url, "max_bytes": max_bytes}, timeout=30)


@tool
def register_artifact(
    path: str,
    title: str,
    config: RunnableConfig,
    kind: Literal["deliverable", "evidence", "report", "archive"] = "deliverable",
    description: str = "",
) -> str:
    """Copy a completed workspace file into immutable reviewable artifact storage."""
    return _post(
        "/v1/artifacts",
        {
            "workspace_id": _workspace_id(config),
            "path": path,
            "title": title,
            "kind": kind,
            "description": description,
        },
    )
