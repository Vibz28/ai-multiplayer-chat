from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from model_router import app as router


def test_route_resolution_uses_compatible_platform_grants(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(router, "AUTH_ROOT", tmp_path)
    codex_auth = tmp_path / "chatgpt" / "codex" / "auth.json"
    codex_auth.parent.mkdir(parents=True)
    codex_auth.write_text("{}", encoding="utf-8")
    pi_auth = tmp_path / "shared" / "pi" / "auth.json"
    pi_auth.parent.mkdir(parents=True)
    pi_auth.write_text(json.dumps({"anthropic": {"type": "oauth"}}), encoding="utf-8")

    assert router.resolve_route(router.RouteRequest(harness="codex"))["provider"] == "chatgpt_subscription"
    assert router.resolve_route(router.RouteRequest(harness="pi"))["provider"] == "claude_subscription"
    assert router.resolve_route(router.RouteRequest(harness="opencode"))["provider"] == "ollama_cloud"


def test_router_rejects_missing_credentials(monkeypatch) -> None:
    monkeypatch.setattr(router, "ROUTER_TOKEN", "router-secret")
    with TestClient(router.app) as client:
        assert client.get("/v1/models").status_code == 403
        response = client.get("/v1/models", headers={"Authorization": "Bearer router-secret"})
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["data"]} == router.ALLOWED_MODELS
        providers = client.get(
            "/v1/providers",
            headers={"X-Fieldwork-Model-Token": "router-secret"},
        )
        assert providers.status_code == 200


def test_delegated_tokens_are_short_lived_and_valid(monkeypatch) -> None:
    monkeypatch.setattr(router, "ROUTER_TOKEN", "router-secret")
    token = router._issue_token(router.TokenRequest(workspace_id="app-test", harness="pi", ttl_seconds=60))
    assert router._valid_delegated_token(token) is True
    assert router._valid_delegated_token(token + "x") is False
