from pathlib import Path

import pytest
from app.agent_tooling import workspace


def test_workspace_tools_write_list_and_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace, "WORKSPACE_ROOT", tmp_path.resolve())

    result = workspace.write_workspace_file.invoke(
        {"relative_path": "deliverables/brief.md", "content": "# Finished brief\n"}
    )

    assert result == "Saved deliverables/brief.md (17 bytes)."
    assert "deliverables [directory]" in workspace.list_workspace.invoke({})
    assert "brief.md [file]" in workspace.list_workspace.invoke(
        {"relative_path": "deliverables"}
    )
    assert workspace.read_workspace_file.invoke(
        {"relative_path": "deliverables/brief.md"}
    ) == "# Finished brief\n"


def test_workspace_tools_reject_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace, "WORKSPACE_ROOT", tmp_path.resolve())

    with pytest.raises(ValueError, match="inside the worker workspace"):
        workspace.write_workspace_file.invoke(
            {"relative_path": "../outside.txt", "content": "not allowed"}
        )
