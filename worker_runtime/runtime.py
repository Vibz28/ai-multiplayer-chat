from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import stat
import tempfile
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

WORKSPACE_ROOT = Path(os.environ.get("WORKER_WORKSPACE_ROOT", "/workspace/jobs")).resolve()
ARTIFACT_ROOT = Path(os.environ.get("WORKER_ARTIFACT_ROOT", "/artifacts")).resolve()
MAX_FILE_BYTES = 10_000_000
MAX_EDIT_BYTES = 500_000
MAX_OUTPUT_BYTES = 200_000
WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ARTIFACT_ID = re.compile(r"^artifact_[0-9a-f-]{36}$")
RUNTIME_TOKEN = os.environ.get("WORKER_RUNTIME_TOKEN", "")
ALLOWED_HARNESS = os.environ.get("WORKER_ALLOWED_HARNESS", "")
MODEL_ROUTER_URL = os.environ.get("WORKER_MODEL_ROUTER_URL", "http://model-router:8181").rstrip("/")
MODEL_ROUTER_TOKEN = os.environ.get("WORKER_MODEL_ROUTER_TOKEN", "")
PLATFORM_AUTH_ROOT = Path(os.environ.get("WORKER_PLATFORM_AUTH_ROOT", "/auth/platform"))
PROCESS_ISOLATION_READY = os.geteuid() == 0
AUTH_PROFILES = {
    ("codex", "chatgpt_subscription"): (
        Path("chatgpt/codex"),
        "codex",
        [Path("auth.json")],
    ),
    ("opencode", "chatgpt_subscription"): (
        Path("chatgpt/opencode"),
        "opencode",
        [Path(".local/share/opencode/auth.json")],
    ),
    ("claude_code", "claude_subscription"): (
        Path("claude/claude-code"),
        "claude",
        [Path(".credentials.json")],
    ),
    ("pi", "chatgpt_subscription"): (
        Path("shared/pi"),
        "pi",
        [Path("auth.json")],
    ),
    ("pi", "claude_subscription"): (
        Path("shared/pi"),
        "pi",
        [Path("auth.json")],
    ),
}

app = FastAPI(title="Fieldwork Worker Runtime")


@app.middleware("http")
async def authenticate_runtime(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    if not PROCESS_ISOLATION_READY:
        return JSONResponse(status_code=503, content={"detail": "process isolation is unavailable"})
    supplied = request.headers.get("x-fieldwork-runtime-token", "")
    if not RUNTIME_TOKEN:
        return JSONResponse(status_code=503, content={"detail": "runtime token is not configured"})
    if not secrets.compare_digest(supplied, RUNTIME_TOKEN):
        return JSONResponse(status_code=403, content={"detail": "invalid runtime token"})
    return await call_next(request)


class WorkspaceRequest(BaseModel):
    workspace_id: str

    @field_validator("workspace_id")
    @classmethod
    def valid_workspace_id(cls, value: str) -> str:
        if not WORKSPACE_ID.fullmatch(value):
            raise ValueError("workspace_id contains unsupported characters")
        return value


class SearchRequest(WorkspaceRequest):
    mode: Literal["paths", "text"] = "paths"
    path: str = "."
    glob: str = "**/*"
    query: str | None = None
    case_sensitive: bool = False
    max_results: int = Field(default=50, ge=1, le=200)


class ReadRequest(WorkspaceRequest):
    path: str
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=400, ge=1, le=1000)


class EditRequest(WorkspaceRequest):
    path: str
    operation: Literal["create", "replace", "overwrite", "delete"]
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content: str | None = None
    old_text: str | None = None
    new_text: str | None = None


class ExecRequest(WorkspaceRequest):
    argv: list[str] = Field(min_length=1, max_length=64)
    cwd: str = "."
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_output_bytes: int = Field(default=100_000, ge=1024, le=MAX_OUTPUT_BYTES)


class FetchRequest(BaseModel):
    url: str
    max_bytes: int = Field(default=200_000, ge=1024, le=1_000_000)


class ArtifactRequest(WorkspaceRequest):
    path: str
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["deliverable", "evidence", "report", "archive"] = "deliverable"
    description: str = Field(default="", max_length=1000)


class HarnessRequest(WorkspaceRequest):
    harness: Literal["codex", "claude_code", "opencode", "pi"]
    prompt: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: int = Field(default=900, ge=10, le=3600)


def _workspace(workspace_id: str) -> Path:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        os.chown(WORKSPACE_ROOT, 0, 0)
    WORKSPACE_ROOT.chmod(0o711)
    root = (WORKSPACE_ROOT / workspace_id).resolve()
    root.relative_to(WORKSPACE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_uid(workspace_id: str) -> int:
    digest = hashlib.sha256(workspace_id.encode()).digest()
    return 100_000 + int.from_bytes(digest[:8], "big") % 2_000_000_000


def _chown_tree(path: Path, uid: int) -> None:
    if os.geteuid() != 0:
        return
    os.chown(path, uid, uid)
    for directory, directories, files in os.walk(path):
        os.chown(directory, uid, uid)
        for name in [*directories, *files]:
            os.chown(Path(directory) / name, uid, uid, follow_symlinks=False)


def _harden_artifact_tree() -> None:
    if os.geteuid() != 0:
        return
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    os.chown(ARTIFACT_ROOT, 0, 0)
    ARTIFACT_ROOT.chmod(0o700)
    for directory in ARTIFACT_ROOT.iterdir():
        if not directory.is_dir() or directory.is_symlink() or not WORKSPACE_ID.fullmatch(directory.name):
            continue
        os.chown(directory, 0, 0)
        directory.chmod(0o700)
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink():
                os.chown(path, 0, 0)
                path.chmod(0o600)


def _prepare_workspace(workspace_id: str) -> tuple[Path, int | None]:
    workspace = _workspace(workspace_id)
    uid = _job_uid(workspace_id) if os.geteuid() == 0 else None
    if uid is not None:
        os.chown(workspace, 0, 0)
        workspace.chmod(0o700)
        _chown_tree(workspace, uid)
    return workspace, uid


def _path(workspace_id: str, relative_path: str, *, must_exist: bool = False) -> Path:
    if not relative_path or Path(relative_path).is_absolute() or "\x00" in relative_path:
        raise HTTPException(status_code=400, detail="path must be relative to the workspace")
    root = _workspace(workspace_id)
    candidate = root / relative_path
    try:
        resolved = candidate.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="path must stay inside the workspace") from exc

    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise HTTPException(status_code=400, detail="symbolic links are not supported")
    return resolved


def _regular_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=400, detail="path must be a regular file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file is too large")


def _read_regular_bytes(path: Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="path must be a regular file") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise HTTPException(status_code=400, detail="path must be a regular file")
        if details.st_size > maximum:
            raise HTTPException(status_code=413, detail="file is too large")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            return source.read(maximum + 1)
    finally:
        os.close(descriptor)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@app.get("/health")
async def health() -> JSONResponse:
    _harden_artifact_tree()
    binaries = {
        name: shutil.which(name) is not None for name in ("claude", "codex", "opencode", "pi", "git", "rg")
    }
    process_isolation = PROCESS_ISOLATION_READY
    healthy = (
        all(binaries.values())
        and process_isolation
        and bool(RUNTIME_TOKEN)
        and bool(MODEL_ROUTER_TOKEN)
    )
    return JSONResponse(status_code=200 if healthy else 503, content={
        "status": "ok" if healthy else "degraded",
        "binaries": binaries,
        "process_isolation": process_isolation,
        "authenticated": bool(RUNTIME_TOKEN),
        "model_router_configured": bool(MODEL_ROUTER_TOKEN),
    })


@app.post("/v1/tools/search")
async def search_workspace(request: SearchRequest) -> dict[str, Any]:
    directory = _path(request.workspace_id, request.path, must_exist=True)
    if not directory.is_dir() or directory.is_symlink():
        raise HTTPException(status_code=400, detail="search path must be a directory")
    if request.mode == "text" and not request.query:
        raise HTTPException(status_code=400, detail="text search requires a query")
    glob_path = Path(request.glob)
    if glob_path.is_absolute() or ".." in glob_path.parts:
        raise HTTPException(status_code=400, detail="glob must stay inside the workspace")

    matches: list[dict[str, Any]] = []
    scanned_files = 0
    for candidate in directory.glob(request.glob):
        if len(matches) >= request.max_results:
            break
        if candidate.is_symlink() or ".git" in candidate.parts:
            continue
        workspace = _workspace(request.workspace_id)
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(workspace).as_posix()
        except (FileNotFoundError, ValueError):
            continue
        candidate = resolved
        if request.mode == "paths":
            matches.append({"path": relative, "kind": "directory" if candidate.is_dir() else "file"})
            continue
        if not candidate.is_file() or candidate.stat().st_size > 2_000_000:
            continue
        scanned_files += 1
        try:
            lines = _read_regular_bytes(candidate, 2_000_000).decode("utf-8").splitlines()
        except (UnicodeDecodeError, HTTPException):
            continue
        query = request.query or ""
        needle = query if request.case_sensitive else query.casefold()
        for line_number, line in enumerate(lines, start=1):
            haystack = line if request.case_sensitive else line.casefold()
            if needle in haystack:
                matches.append({"path": relative, "line": line_number, "text": line[:1000]})
                if len(matches) >= request.max_results:
                    break
    return {"matches": matches, "scanned_files": scanned_files, "truncated": len(matches) >= request.max_results}


@app.post("/v1/tools/read")
async def read_workspace(request: ReadRequest) -> dict[str, Any]:
    target = _path(request.workspace_id, request.path, must_exist=True)
    _regular_file(target)
    data = _read_regular_bytes(target)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="file is not UTF-8 text") from exc
    lines = text.splitlines(keepends=True)
    start = min(request.start_line - 1, len(lines))
    selected = "".join(lines[start : start + request.max_lines])
    return {
        "path": request.path,
        "start_line": start + 1,
        "end_line": min(start + request.max_lines, len(lines)),
        "total_lines": len(lines),
        "content": selected[:MAX_OUTPUT_BYTES],
        "sha256": _digest(data),
        "truncated": start + request.max_lines < len(lines) or len(selected) > MAX_OUTPUT_BYTES,
    }


@app.post("/v1/tools/edit")
async def edit_workspace(request: EditRequest) -> dict[str, Any]:
    target = _path(request.workspace_id, request.path)
    before = _read_regular_bytes(target) if target.exists() else None
    if before is not None:
        _regular_file(target)
    before_hash = _digest(before) if before is not None else None

    if request.operation == "create":
        if before is not None or request.content is None:
            raise HTTPException(status_code=409, detail="create requires content and a new path")
        updated = request.content.encode()
    elif request.operation == "replace":
        if before is None or request.old_text is None or request.new_text is None:
            raise HTTPException(status_code=400, detail="replace requires an existing file and old/new text")
        if request.expected_sha256 != before_hash:
            raise HTTPException(status_code=409, detail="file changed since it was read")
        current = before.decode("utf-8")
        if not request.old_text or current.count(request.old_text) != 1:
            raise HTTPException(status_code=409, detail="old_text must occur exactly once")
        updated = current.replace(request.old_text, request.new_text, 1).encode()
    elif request.operation == "overwrite":
        if before is None or request.content is None or request.expected_sha256 != before_hash:
            raise HTTPException(status_code=409, detail="overwrite requires the current file hash")
        updated = request.content.encode()
    else:
        if before is None or request.expected_sha256 != before_hash:
            raise HTTPException(status_code=409, detail="delete requires the current file hash")
        target.unlink()
        return {"path": request.path, "operation": "delete", "before_sha256": before_hash, "after_sha256": None}

    if len(updated) > MAX_EDIT_BYTES:
        raise HTTPException(status_code=413, detail="edited file exceeds the 500 KB limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as temporary:
        temporary.write(updated)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, target)
    return {
        "path": request.path,
        "operation": request.operation,
        "before_sha256": before_hash,
        "after_sha256": _digest(updated),
        "bytes": len(updated),
    }


async def _run_process(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    run_uid: int | None = None,
    output_limit: int = MAX_OUTPUT_BYTES,
    keep_output_tail: bool = False,
) -> dict[str, Any]:
    demote = None
    if run_uid is not None:
        def demote() -> None:
            os.setgroups([])
            os.setgid(run_uid)
            os.setuid(run_uid)

    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        preexec_fn=demote,
    )

    async def read_bounded(stream: asyncio.StreamReader | None) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        captured = bytearray()
        total = 0
        while chunk := await stream.read(65_536):
            total += len(chunk)
            if keep_output_tail:
                captured.extend(chunk)
                if len(captured) > output_limit:
                    del captured[: len(captured) - output_limit]
            elif len(captured) < output_limit:
                captured.extend(chunk[: output_limit - len(captured)])
        return bytes(captured), total > output_limit

    stdout_task = asyncio.create_task(read_bounded(process.stdout))
    stderr_task = asyncio.create_task(read_bounded(process.stderr))
    if process.stdin is not None:
        if stdin is not None:
            process.stdin.write(stdin.encode())
            await process.stdin.drain()
        process.stdin.close()
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
        timed_out = False
    except TimeoutError:
        os.killpg(process.pid, 9)
        await process.wait()
        timed_out = True
    (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
        stdout_task, stderr_task
    )
    return {
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "stdout_bytes": stdout,
        "stderr_bytes": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


@app.post("/v1/tools/exec")
async def execute_workspace(request: ExecRequest) -> dict[str, Any]:
    cwd = _path(request.workspace_id, request.cwd, must_exist=True)
    if not cwd.is_dir():
        raise HTTPException(status_code=400, detail="cwd must be a directory")
    workspace, run_uid = _prepare_workspace(request.workspace_id)
    clean_home = workspace / ".worker-home"
    clean_home.mkdir(exist_ok=True)
    if run_uid is not None:
        _chown_tree(clean_home, run_uid)
    env = {
        "HOME": str(clean_home),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "TMPDIR": "/tmp",
    }
    try:
        result = await _run_process(
            request.argv,
            cwd=cwd,
            timeout=request.timeout_seconds,
            env=env,
            run_uid=run_uid,
            output_limit=request.max_output_bytes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail="command was not found") from exc
    stdout = result.pop("stdout_bytes").decode("utf-8", errors="replace")
    stderr = result.pop("stderr_bytes").decode("utf-8", errors="replace")
    stdout_truncated = bool(result.pop("stdout_truncated"))
    stderr_truncated = bool(result.pop("stderr_truncated"))
    return {
        **result,
        "argv": request.argv,
        "cwd": request.cwd,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


async def _public_host(hostname: str) -> None:
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="URL host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise HTTPException(status_code=400, detail="URL must resolve to a public address")


@app.post("/v1/tools/fetch")
async def fetch_public_url(request: FetchRequest) -> dict[str, Any]:
    parsed = urlparse(request.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="only public HTTP and HTTPS URLs are supported")
    await _public_host(parsed.hostname)
    content = bytearray()
    truncated = False
    async with httpx.AsyncClient(follow_redirects=False, timeout=20, trust_env=False) as client:
        async with client.stream(
            "GET",
            request.url,
            headers={"User-Agent": "Fieldwork-Moss/1.0"},
        ) as response:
            response.raise_for_status()
            network_stream = response.extensions.get("network_stream")
            peer = network_stream.get_extra_info("server_addr") if network_stream else None
            if peer and not ipaddress.ip_address(peer[0]).is_global:
                raise HTTPException(status_code=400, detail="URL connected to a non-public address")
            async for chunk in response.aiter_bytes():
                remaining = request.max_bytes + 1 - len(content)
                if remaining <= 0:
                    truncated = True
                    break
                content.extend(chunk[:remaining])
                if len(content) > request.max_bytes:
                    truncated = True
                    break
            response_url = str(response.url)
            status_code = response.status_code
            content_type = response.headers.get("content-type", "")
    bounded_content = bytes(content[: request.max_bytes])
    return {
        "url": response_url,
        "status_code": status_code,
        "content_type": content_type,
        "content": bounded_content.decode("utf-8", errors="replace"),
        "truncated": truncated,
    }


@app.post("/v1/artifacts")
async def register_artifact(request: ArtifactRequest) -> dict[str, Any]:
    source = _path(request.workspace_id, request.path, must_exist=True)
    data = _read_regular_bytes(source)
    artifact_id = f"artifact_{uuid4()}"
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        os.chown(ARTIFACT_ROOT, 0, 0)
    ARTIFACT_ROOT.chmod(0o700)
    destination_dir = ARTIFACT_ROOT / request.workspace_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        os.chown(destination_dir, 0, 0)
    destination_dir.chmod(0o700)
    content_hash = _digest(data)
    destination = destination_dir / f"{artifact_id}.data"
    destination.write_bytes(data)
    destination.chmod(0o600)
    metadata = {
        "artifact_id": artifact_id,
        "filename": source.name,
        "title": request.title,
        "description": request.description,
        "kind": request.kind,
        "media_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        "size_bytes": len(data),
        "sha256": content_hash,
        "download_ref": f"artifact:{artifact_id}",
        "immutable": True,
    }
    metadata_path = destination_dir / f"{artifact_id}.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True), encoding="utf-8"
    )
    metadata_path.chmod(0o600)
    if os.geteuid() == 0:
        os.chown(destination, 0, 0)
        os.chown(metadata_path, 0, 0)
    return metadata


@app.get("/v1/artifacts/{workspace_id}")
async def list_artifacts(workspace_id: str) -> dict[str, Any]:
    WorkspaceRequest(workspace_id=workspace_id)
    directory = ARTIFACT_ROOT / workspace_id
    if not directory.exists():
        return {"items": [], "count": 0}
    items: list[dict[str, Any]] = []
    for metadata_path in sorted(directory.glob("artifact_*.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(metadata, dict):
            items.append(metadata)
    return {"items": items, "count": len(items)}


@app.get("/v1/artifacts/{workspace_id}/{artifact_id}/content")
async def download_artifact(workspace_id: str, artifact_id: str) -> FileResponse:
    WorkspaceRequest(workspace_id=workspace_id)
    if not ARTIFACT_ID.fullmatch(artifact_id):
        raise HTTPException(status_code=404, detail="artifact not found")
    directory = ARTIFACT_ROOT / workspace_id
    data_path = directory / f"{artifact_id}.data"
    metadata_path = directory / f"{artifact_id}.json"
    if not data_path.is_file() or not metadata_path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return FileResponse(
        data_path,
        media_type=str(metadata.get("media_type", "application/octet-stream")),
        filename=str(metadata.get("filename", "deliverable")),
    )


async def _resolve_harness_route(harness: str) -> dict[str, Any]:
    if not MODEL_ROUTER_TOKEN:
        raise HTTPException(status_code=503, detail="model router token is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{MODEL_ROUTER_URL}/v1/routes/resolve",
                json={"harness": harness, "preferred_provider": "auto"},
                headers={"X-Fieldwork-Model-Token": MODEL_ROUTER_TOKEN},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="model router is unavailable") from exc
    route = response.json()
    if not isinstance(route, dict) or not route.get("available"):
        reason = route.get("reason") if isinstance(route, dict) else None
        raise HTTPException(status_code=409, detail=str(reason or "no compatible model route is available"))
    return route


async def _delegated_model_token(workspace_id: str, harness: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{MODEL_ROUTER_URL}/v1/tokens",
                json={"workspace_id": workspace_id, "harness": harness, "ttl_seconds": 3600},
                headers={"X-Fieldwork-Model-Token": MODEL_ROUTER_TOKEN},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="model router could not issue a run token") from exc
    token = response.json().get("token")
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=502, detail="model router returned an invalid run token")
    return token


def _configure_gateway_auth(
    harness: str,
    auth_home: Path,
    *,
    model: str,
    token: str,
) -> None:
    if harness == "opencode":
        config = {
            "$schema": "https://opencode.ai/config.json",
            "model": f"fieldwork/{model}",
            "small_model": f"fieldwork/{model}",
            "share": "disabled",
            "provider": {
                "fieldwork": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Fieldwork Model Router",
                    "options": {"baseURL": f"{MODEL_ROUTER_URL}/v1", "apiKey": token},
                    "models": {model: {"name": model}},
                }
            },
        }
        config_path = auth_home / ".config" / "opencode" / "opencode.json"
    else:
        config = {
            "providers": {
                "fieldwork": {
                    "baseUrl": f"{MODEL_ROUTER_URL}/v1",
                    "api": "openai-completions",
                    "apiKey": token,
                    "authHeader": True,
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [
                        {
                            "id": model,
                            "name": model,
                            "reasoning": True,
                            "contextWindow": 131072,
                            "maxTokens": 32768,
                        }
                    ],
                }
            }
        }
        config_path = auth_home / "models.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=True), encoding="utf-8")
    config_path.chmod(0o600)


def _harness_command(
    harness: str,
    workspace: Path,
    prompt: str,
    auth_home: Path | None = None,
    route: dict[str, Any] | None = None,
) -> tuple[list[str], str | None, dict[str, str]]:
    base_env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TMPDIR": "/tmp"}
    model = str(route.get("model") or "") if route else ""
    provider = str(route.get("provider", "")) if route else ""
    mode = str(route.get("mode", "native_subscription")) if route else "native_subscription"
    if harness == "codex":
        home = str(auth_home or Path("/auth/codex"))
        env = {**base_env, "HOME": home, "CODEX_HOME": home}
        argv = [
            "codex", "exec", "-C", str(workspace), "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--skip-git-repo-check", "--sandbox", "danger-full-access", "-c",
            'approval_policy="never"', "--json", "-",
        ]
        if model:
            argv[2:2] = ["--model", model]
        return argv, prompt, env
    if harness == "claude_code":
        home = str(auth_home or Path("/auth/claude"))
        env = {**base_env, "HOME": home, "CLAUDE_CONFIG_DIR": home}
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        argv = [
            "claude", "--safe-mode", "-p", prompt, "--allowedTools", "Read,Edit,Write,Bash,Glob,Grep",
            "--output-format", "json",
        ]
        if model:
            argv[1:1] = ["--model", model]
        return argv, None, env
    if harness == "opencode":
        env = {**base_env, "HOME": str(auth_home or Path("/auth/opencode"))}
        argv = ["opencode", "run", "--dir", str(workspace), "--format", "json", "--auto", "--pure"]
        if model:
            selected_model = f"fieldwork/{model}" if mode == "gateway" else f"openai/{model}"
            argv.extend(["--model", selected_model])
        argv.append(prompt)
        return argv, None, env
    home = str(auth_home or Path("/auth/pi"))
    env = {**base_env, "HOME": home, "PI_CODING_AGENT_DIR": home}
    argv = [
        "pi", "--print", "--mode", "json", "--no-session", "--no-approve", "--no-extensions", "--no-skills",
        "--no-prompt-templates", "--no-context-files",
    ]
    if mode == "gateway":
        argv.extend(["--provider", "fieldwork", "--model", model])
    elif provider == "chatgpt_subscription":
        argv.extend(["--provider", "openai-codex", "--model", model])
    elif provider == "claude_subscription":
        argv.extend(["--provider", "anthropic", "--model", model])
    argv.append(prompt)
    return argv, None, env


def _extract_result(harness: str, output: str) -> str:
    candidates: list[tuple[int, str]] = []

    def collect(value: Any, priority: int = 0) -> None:
        if isinstance(value, list):
            for item in value:
                collect(item, priority)
            return
        if not isinstance(value, dict):
            return
        event_type = str(value.get("type", ""))
        role = str(value.get("role", ""))
        for key, item in value.items():
            if isinstance(item, str) and item.strip():
                if key in {"result", "final_output"}:
                    candidates.append((4, item.strip()))
                elif key in {"text", "content"} and (
                    event_type in {"agent_message", "text", "result"} or role == "assistant"
                ):
                    candidates.append((3, item.strip()))
                elif key == "message" and event_type in {"result", "assistant"}:
                    candidates.append((2, item.strip()))
            elif isinstance(item, (dict, list)):
                collect(item, priority)

    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        collect(payload)
    if candidates:
        best_priority = max(priority for priority, _ in candidates)
        return [text for priority, text in candidates if priority == best_priority][-1]
    return output.strip()[-MAX_OUTPUT_BYTES:] or f"{harness} finished without a written summary."


@app.post("/v1/harness/run")
async def run_harness(request: HarnessRequest) -> dict[str, Any]:
    if ALLOWED_HARNESS != request.harness:
        raise HTTPException(status_code=403, detail="harness is not enabled in this runtime")
    if os.geteuid() == 0:
        PLATFORM_AUTH_ROOT.mkdir(parents=True, exist_ok=True)
        os.chown(PLATFORM_AUTH_ROOT, 0, 0)
        PLATFORM_AUTH_ROOT.chmod(0o700)
    route = await _resolve_harness_route(request.harness)
    workspace, run_uid = _prepare_workspace(request.workspace_id)
    auth_names = {"codex": "codex", "claude_code": "claude", "opencode": "opencode", "pi": "pi"}
    profile = AUTH_PROFILES.get((request.harness, str(route.get("provider", ""))))
    persistent_auth = PLATFORM_AUTH_ROOT / profile[0] if profile else None
    auth_files = profile[2] if profile else []
    if persistent_auth is not None and os.geteuid() == 0:
        persistent_auth.mkdir(parents=True, exist_ok=True)
        os.chown(persistent_auth, 0, 0)
        persistent_auth.chmod(0o700)
    run_auth_parent = Path(tempfile.mkdtemp(prefix=f"fieldwork-{request.harness}-"))
    run_auth = run_auth_parent / auth_names[request.harness]
    run_auth.mkdir(parents=True)
    for relative_path in auth_files:
        source = persistent_auth / relative_path  # type: ignore[operator]
        if source.is_file() and not source.is_symlink():
            destination = run_auth / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    if route.get("mode") == "gateway":
        delegated_token = await _delegated_model_token(request.workspace_id, request.harness)
        _configure_gateway_auth(
            request.harness,
            run_auth,
            model=str(route["model"]),
            token=delegated_token,
        )
    if run_uid is not None:
        run_auth_parent.chmod(0o700)
        _chown_tree(run_auth_parent, run_uid)
    argv, stdin, env = _harness_command(
        request.harness,
        workspace,
        request.prompt,
        run_auth,
        route,
    )
    try:
        result = await _run_process(
            argv,
            cwd=workspace,
            timeout=request.timeout_seconds,
            stdin=stdin,
            env=env,
            run_uid=run_uid,
            output_limit=1_000_000,
            keep_output_tail=True,
        )
    finally:
        for relative_path in auth_files:
            source = run_auth / relative_path
            if source.is_file() and not source.is_symlink():
                destination = persistent_auth / relative_path  # type: ignore[operator]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        if persistent_auth is not None and os.geteuid() == 0:
            _chown_tree(persistent_auth, 0)
            persistent_auth.chmod(0o700)
        shutil.rmtree(run_auth_parent, ignore_errors=True)
    stdout = result.pop("stdout_bytes").decode("utf-8", errors="replace")
    stderr = result.pop("stderr_bytes").decode("utf-8", errors="replace")
    stdout_truncated = bool(result.pop("stdout_truncated"))
    stderr_truncated = bool(result.pop("stderr_truncated"))
    if result["exit_code"] != 0 or result["timed_out"]:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"{request.harness} could not complete the assignment",
                "exit_code": result["exit_code"],
                "timed_out": result["timed_out"],
                "stderr": stderr,
            },
        )
    artifacts: list[dict[str, Any]] = []
    deliverables = workspace / "deliverables"
    if deliverables.is_dir():
        for candidate in sorted(deliverables.rglob("*"))[:50]:
            if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_size <= MAX_FILE_BYTES:
                relative = candidate.relative_to(workspace).as_posix()
                artifact = await register_artifact(
                    ArtifactRequest(
                        workspace_id=request.workspace_id,
                        path=relative,
                        title=candidate.stem.replace("-", " ").replace("_", " ").title(),
                        kind="deliverable",
                        description=f"Created by the {request.harness} harness.",
                    )
                )
                artifacts.append(artifact)
    return {
        **result,
        "harness": request.harness,
        "route": route,
        "answer_markdown": _extract_result(request.harness, stdout),
        "artifacts": artifacts,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }
