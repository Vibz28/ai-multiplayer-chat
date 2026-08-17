from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from worker_runtime import runtime


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(runtime, "WORKSPACE_ROOT", (tmp_path / "jobs").resolve())
    monkeypatch.setattr(runtime, "ARTIFACT_ROOT", (tmp_path / "artifacts").resolve())
    monkeypatch.setattr(runtime, "RUNTIME_TOKEN", "test-runtime-token")
    monkeypatch.setattr(runtime, "PROCESS_ISOLATION_READY", True)
    return TestClient(
        runtime.app,
        headers={"X-Fieldwork-Runtime-Token": "test-runtime-token"},
    )


def test_workspace_create_read_replace_search_and_artifact(client: TestClient) -> None:
    created = client.post(
        "/v1/tools/edit",
        json={
            "workspace_id": "app-test",
            "path": "deliverables/brief.md",
            "operation": "create",
            "content": "Kickoff brief\nOwner: Moss\n",
        },
    )
    assert created.status_code == 200

    read = client.post(
        "/v1/tools/read",
        json={"workspace_id": "app-test", "path": "deliverables/brief.md"},
    )
    assert read.status_code == 200
    assert read.json()["content"] == "Kickoff brief\nOwner: Moss\n"

    replaced = client.post(
        "/v1/tools/edit",
        json={
            "workspace_id": "app-test",
            "path": "deliverables/brief.md",
            "operation": "replace",
            "expected_sha256": read.json()["sha256"],
            "old_text": "Owner: Moss",
            "new_text": "Owner: Team",
        },
    )
    assert replaced.status_code == 200

    search = client.post(
        "/v1/tools/search",
        json={
            "workspace_id": "app-test",
            "mode": "text",
            "query": "owner: team",
        },
    )
    assert search.status_code == 200
    assert search.json()["matches"][0]["line"] == 2

    artifact = client.post(
        "/v1/artifacts",
        json={
            "workspace_id": "app-test",
            "path": "deliverables/brief.md",
            "title": "Kickoff brief",
        },
    )
    assert artifact.status_code == 200
    assert artifact.json()["immutable"] is True
    assert artifact.json()["download_ref"].startswith("artifact:")

    duplicate = client.post(
        "/v1/artifacts",
        json={
            "workspace_id": "app-test",
            "path": "deliverables/brief.md",
            "title": "Kickoff brief",
        },
    )
    assert duplicate.json()["artifact_id"] != artifact.json()["artifact_id"]

    listed = client.get("/v1/artifacts/app-test")
    assert listed.status_code == 200
    assert listed.json()["count"] == 2
    assert listed.json()["items"][0]["title"] == "Kickoff brief"

    downloaded = client.get(
        f"/v1/artifacts/app-test/{artifact.json()['artifact_id']}/content"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"Kickoff brief\nOwner: Team\n"


def test_workspace_rejects_escape_and_stale_edit(client: TestClient) -> None:
    escaped = client.post(
        "/v1/tools/edit",
        json={
            "workspace_id": "app-test",
            "path": "../outside.txt",
            "operation": "create",
            "content": "no",
        },
    )
    assert escaped.status_code == 400
    escaped_glob = client.post(
        "/v1/tools/search",
        json={"workspace_id": "app-test", "mode": "paths", "glob": "../*"},
    )
    assert escaped_glob.status_code == 400

    created = client.post(
        "/v1/tools/edit",
        json={
            "workspace_id": "app-test",
            "path": "safe.txt",
            "operation": "create",
            "content": "safe",
        },
    )
    assert created.status_code == 200
    stale = client.post(
        "/v1/tools/edit",
        json={
            "workspace_id": "app-test",
            "path": "safe.txt",
            "operation": "overwrite",
            "expected_sha256": "0" * 64,
            "content": "changed",
        },
    )
    assert stale.status_code == 409


def test_workspace_exec_preserves_arguments_without_a_shell(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/exec",
        json={
            "workspace_id": "app-test",
            "argv": [sys.executable, "-c", "import sys; print(sys.argv[1])", "a; echo unsafe"],
        },
    )
    assert response.status_code == 200
    assert response.json()["exit_code"] == 0
    assert response.json()["stdout"] == "a; echo unsafe\n"


def test_runtime_api_rejects_missing_internal_token(client: TestClient) -> None:
    response = client.post(
        "/v1/tools/read",
        headers={"X-Fieldwork-Runtime-Token": ""},
        json={"workspace_id": "app-test", "path": "safe.txt"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("harness", ["codex", "claude_code", "opencode", "pi"])
def test_harness_commands_are_direct_argv(harness: str, tmp_path: Path) -> None:
    argv, stdin, _ = runtime._harness_command(harness, tmp_path, "do the work")
    assert argv[0] in {"codex", "claude", "opencode", "pi"}
    assert argv[0] not in {"sh", "bash"}
    if harness == "codex":
        assert stdin == "do the work"


def test_codex_uses_subscription_default_when_route_has_no_model(tmp_path: Path) -> None:
    route = {"mode": "native_subscription", "provider": "chatgpt_subscription", "model": None}
    argv, _, _ = runtime._harness_command("codex", tmp_path, "test", route=route)

    assert "--model" not in argv


@pytest.mark.parametrize(
    ("harness", "output", "expected"),
    [
        ("claude_code", '{"type":"result","result":"Claude result"}', "Claude result"),
        (
            "codex",
            '{"type":"item.completed","item":{"type":"agent_message","text":"Codex result"}}',
            "Codex result",
        ),
        ("opencode", '{"type":"text","part":{"type":"text","text":"OpenCode result"}}', "OpenCode result"),
        (
            "pi",
            '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"Pi result"}]}}',
            "Pi result",
        ),
    ],
)
def test_extracts_native_harness_result(harness: str, output: str, expected: str) -> None:
    assert runtime._extract_result(harness, output) == expected


@pytest.mark.parametrize("harness", ["opencode", "pi"])
def test_gateway_harnesses_receive_router_config(harness: str, tmp_path: Path) -> None:
    auth_home = tmp_path / harness
    auth_home.mkdir()
    runtime._configure_gateway_auth(
        harness,
        auth_home,
        model="gpt-oss:120b-cloud",
        token="delegated-token",
    )
    route = {
        "mode": "gateway",
        "provider": "ollama_cloud",
        "model": "gpt-oss:120b-cloud",
    }
    argv, _, _ = runtime._harness_command(harness, tmp_path, "test", auth_home, route)

    assert any("gpt-oss:120b-cloud" in argument for argument in argv)
    if harness == "opencode":
        config = auth_home / ".config/opencode/opencode.json"
        assert "delegated-token" in config.read_text(encoding="utf-8")
    else:
        config = auth_home / "models.json"
        assert "http://model-router:8181/v1" in config.read_text(encoding="utf-8")
