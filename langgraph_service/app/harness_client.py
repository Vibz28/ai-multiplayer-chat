from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.schemas import AgentRunRequest


async def run_harness(request: AgentRunRequest) -> dict[str, Any]:
    settings = get_settings()
    runtime_urls = {
        "codex": settings.codex_runtime_url,
        "claude_code": settings.claude_runtime_url,
        "opencode": settings.opencode_runtime_url,
        "pi": settings.pi_runtime_url,
    }
    runtime_url = runtime_urls.get(request.harness)
    if runtime_url is None:
        raise RuntimeError("unsupported harness")
    payload = {
        "workspace_id": request.application_id,
        "harness": request.harness,
        "prompt": (
            "You are Moss, a digital worker in an isolated workspace. Complete the requested work "
            "using the harness tools available to you. Put reviewable standalone outputs under "
            "deliverables/. Do not publish, deploy, push, or claim access outside this workspace. "
            "Finish with a plain-language summary of outcomes, files, verification, and anything "
            "requiring human review.\n\nAssignment:\n" + request.message
        ),
        "timeout_seconds": 900,
    }
    async with httpx.AsyncClient(timeout=920) as client:
        response = await client.post(
            f"{runtime_url.rstrip('/')}/v1/harness/run",
            json=payload,
            headers={"X-Fieldwork-Runtime-Token": settings.runtime_token},
        )
        response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("worker runtime returned an invalid harness result")
    return result
