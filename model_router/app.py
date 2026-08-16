from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

ROUTER_TOKEN = os.environ.get("MODEL_ROUTER_TOKEN", "")
UPSTREAM_URL = os.environ.get("MODEL_ROUTER_OLLAMA_CLOUD_URL", "http://host.docker.internal:11434").rstrip("/")
PRIMARY_MODEL = os.environ.get("MODEL_ROUTER_PRIMARY_MODEL", "kimi-k2.7-code:cloud")
FALLBACK_MODEL = os.environ.get("MODEL_ROUTER_FALLBACK_MODEL", "gpt-oss:120b-cloud")
CHATGPT_SUBSCRIPTION_MODEL = os.environ.get("MODEL_ROUTER_CHATGPT_MODEL", "gpt-5.3-codex")
CLAUDE_SUBSCRIPTION_MODEL = os.environ.get("MODEL_ROUTER_CLAUDE_MODEL", "claude-sonnet-4-6")
AUTH_ROOT = Path(os.environ.get("MODEL_ROUTER_AUTH_ROOT", "/auth/platform"))
ALLOWED_MODELS = {PRIMARY_MODEL, FALLBACK_MODEL}

app = FastAPI(title="Fieldwork Model Router")


class RouteRequest(BaseModel):
    harness: Literal["langgraph", "codex", "claude_code", "opencode", "pi"]
    preferred_provider: Literal["auto", "chatgpt_subscription", "claude_subscription", "ollama_cloud"] = "auto"


class TokenRequest(BaseModel):
    workspace_id: str
    harness: Literal["opencode", "pi"]
    ttl_seconds: int = 3600


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _issue_token(request: TokenRequest) -> str:
    payload = {
        "workspace_id": request.workspace_id,
        "harness": request.harness,
        "models": sorted(ALLOWED_MODELS),
        "exp": int(time.time()) + min(max(request.ttl_seconds, 60), 3600),
    }
    encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64(hmac.new(ROUTER_TOKEN.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"fwrt.{encoded}.{signature}"


def _valid_delegated_token(token: str) -> bool:
    try:
        prefix, encoded, supplied_signature = token.split(".", 2)
        expected = _b64(hmac.new(ROUTER_TOKEN.encode(), encoded.encode(), hashlib.sha256).digest())
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        return (
            prefix == "fwrt"
            and secrets.compare_digest(supplied_signature, expected)
            and int(payload.get("exp", 0)) >= int(time.time())
            and set(payload.get("models", [])) <= ALLOWED_MODELS
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


def _master_authorized(request: Request) -> bool:
    supplied = request.headers.get("x-fieldwork-model-token", "")
    return bool(ROUTER_TOKEN) and secrets.compare_digest(supplied, ROUTER_TOKEN)


def _model_authorized(request: Request) -> bool:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or not ROUTER_TOKEN:
        return False
    return secrets.compare_digest(token, ROUTER_TOKEN) or _valid_delegated_token(token)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    if request.url.path in {"/v1/providers", "/v1/routes/resolve", "/v1/tokens"}:
        authorized = _master_authorized(request)
    else:
        authorized = _model_authorized(request)
    if not ROUTER_TOKEN:
        return JSONResponse(status_code=503, content={"detail": "model router token is not configured"})
    if not authorized:
        return JSONResponse(status_code=403, content={"detail": "invalid model router credential"})
    return await call_next(request)


def _pi_grants() -> set[str]:
    auth_file = AUTH_ROOT / "shared" / "pi" / "auth.json"
    try:
        payload = json.loads(auth_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()
    return set(payload) if isinstance(payload, dict) else set()


def provider_status() -> dict[str, dict[str, Any]]:
    pi_grants = _pi_grants()
    return {
        "chatgpt_subscription": {
            "configured": any([
                (AUTH_ROOT / "chatgpt" / "codex" / "auth.json").is_file(),
                (AUTH_ROOT / "chatgpt" / "opencode" / ".local/share/opencode/auth.json").is_file(),
                "openai-codex" in pi_grants,
            ]),
            "harness_grants": {
                "codex": (AUTH_ROOT / "chatgpt" / "codex" / "auth.json").is_file(),
                "opencode": (AUTH_ROOT / "chatgpt" / "opencode" / ".local/share/opencode/auth.json").is_file(),
                "pi": "openai-codex" in pi_grants,
            },
        },
        "claude_subscription": {
            "configured": any([
                (AUTH_ROOT / "claude" / "claude-code" / ".credentials.json").is_file(),
                bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
                "anthropic" in pi_grants,
            ]),
            "harness_grants": {
                "claude_code": (
                    (AUTH_ROOT / "claude" / "claude-code" / ".credentials.json").is_file()
                    or bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
                ),
                "pi": "anthropic" in pi_grants,
            },
        },
        "ollama_cloud": {
            "configured": True,
            "harness_grants": {"langgraph": True, "opencode": True, "pi": True},
        },
    }


def resolve_route(request: RouteRequest) -> dict[str, Any]:
    status = provider_status()
    grant_order = {
        "langgraph": ["ollama_cloud"],
        "codex": ["chatgpt_subscription"],
        "claude_code": ["claude_subscription"],
        "opencode": ["chatgpt_subscription", "ollama_cloud"],
        "pi": ["chatgpt_subscription", "claude_subscription", "ollama_cloud"],
    }
    providers = grant_order[request.harness]
    if request.preferred_provider != "auto":
        providers = [request.preferred_provider]
    for provider in providers:
        grants = status.get(provider, {}).get("harness_grants", {})
        if not grants.get(request.harness):
            continue
        if provider == "ollama_cloud":
            return {
                "available": True,
                "harness": request.harness,
                "mode": "gateway",
                "provider": provider,
                "model": FALLBACK_MODEL,
                "credential_profile": None,
            }
        return {
            "available": True,
            "harness": request.harness,
            "mode": "native_subscription",
            "provider": provider,
            "model": (
                CHATGPT_SUBSCRIPTION_MODEL
                if provider == "chatgpt_subscription"
                else CLAUDE_SUBSCRIPTION_MODEL
            ),
            "credential_profile": f"{provider}/{request.harness}",
        }
    return {
        "available": False,
        "harness": request.harness,
        "mode": "unavailable",
        "provider": providers[0],
        "model": None,
        "credential_profile": None,
        "reason": f"No compatible {providers[0]} grant is configured for {request.harness}.",
    }


@app.get("/health")
async def health() -> JSONResponse:
    upstream_ok = False
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(f"{UPSTREAM_URL}/api/tags")
            upstream_ok = response.is_success
    except httpx.HTTPError:
        pass
    healthy = bool(ROUTER_TOKEN) and upstream_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "upstream": "ollama_cloud",
            "upstream_reachable": upstream_ok,
            "models": sorted(ALLOWED_MODELS),
            "providers": provider_status(),
        },
    )


@app.post("/v1/routes/resolve")
async def route(request: RouteRequest) -> dict[str, Any]:
    return resolve_route(request)


@app.get("/v1/providers")
async def providers() -> dict[str, Any]:
    return {"providers": provider_status()}


@app.post("/v1/tokens")
async def token(request: TokenRequest) -> dict[str, Any]:
    return {"token": _issue_token(request), "expires_in": min(max(request.ttl_seconds, 60), 3600)}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": model, "object": "model", "owned_by": "ollama-cloud"}
            for model in sorted(ALLOWED_MODELS)
        ],
    }


async def _proxy(request: Request, upstream_path: str) -> Response:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="request body must be JSON") from exc
    if not isinstance(body, dict) or body.get("model") not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail="model is not in the Fieldwork cloud allowlist")
    stream = bool(body.get("stream"))
    if not stream:
        async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
            upstream = await client.post(f"{UPSTREAM_URL}{upstream_path}", json=body)
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )

    client = httpx.AsyncClient(timeout=300, trust_env=False)
    context = client.stream("POST", f"{UPSTREAM_URL}{upstream_path}", json=body)
    upstream = await context.__aenter__()
    if not upstream.is_success:
        content = await upstream.aread()
        await context.__aexit__(None, None, None)
        await client.aclose()
        return Response(content=content, status_code=upstream.status_code)

    async def chunks():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await context.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(chunks(), media_type=upstream.headers.get("content-type"))


@app.post("/api/chat")
async def ollama_chat(request: Request) -> Response:
    return await _proxy(request, "/api/chat")


@app.post("/api/show")
async def ollama_show(request: Request) -> Response:
    return await _proxy(request, "/api/show")


@app.post("/v1/chat/completions")
async def openai_chat(request: Request) -> Response:
    return await _proxy(request, "/v1/chat/completions")
