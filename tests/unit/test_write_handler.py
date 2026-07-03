"""
Unit tests for the write handler.
Zero disk I/O against real workspace — uses tmp_path pytest fixture.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.action.handlers.write_handler import write_json_file
from shared.exceptions import ActionExecutionError, PathTraversalError, InvalidExtensionError


@pytest.fixture(autouse=True)
def patch_workspace(tmp_path: Path):
    """Redirect WORKSPACE_ROOT to a temp dir for every test."""
    fake_workspace = tmp_path / "workspace"
    fake_workspace.mkdir()
    with (
        patch("services.action.handlers.write_handler.WORKSPACE_ROOT", fake_workspace),
        patch("services.action.safety.path_validator.WORKSPACE_ROOT", fake_workspace),
        patch("services.action.safety.backup.WORKSPACE_ROOT", fake_workspace, create=True),
    ):
        yield fake_workspace


class TestWriteJsonFile:
    def test_creates_new_file(self, patch_workspace: Path) -> None:
        result = write_json_file("output.json", {"key": "value"})
        assert result["success"] is True
        written = (patch_workspace / "output.json").read_text()
        assert json.loads(written) == {"key": "value"}

    def test_creates_backup_on_overwrite(self, patch_workspace: Path) -> None:
        (patch_workspace / "output.json").write_text('{"old": true}')
        result = write_json_file("output.json", {"new": True})
        assert result["backup_path"] is not None
        assert Path(result["backup_path"]).exists()

    def test_no_backup_for_new_file(self, patch_workspace: Path) -> None:
        result = write_json_file("new_file.json", {"x": 1})
        assert result["backup_path"] is None

    def test_rejects_non_dict_content(self, patch_workspace: Path) -> None:
        with pytest.raises(ActionExecutionError):
            write_json_file("output.json", "not a dict")  # type: ignore[arg-type]

    def test_bytes_written_matches_file_size(self, patch_workspace: Path) -> None:
        content = {"hello": "world"}
        result = write_json_file("bytes_test.json", content)
        actual_size = (patch_workspace / "bytes_test.json").stat().st_size
        assert result["bytes_written"] == actual_size


class TestWriteHandlerSafety:
    """Safety tests that work through the validator."""

    def test_traversal_blocked(self, patch_workspace: Path) -> None:
        with pytest.raises(PathTraversalError):
            write_json_file("../../etc/shadow.json", {})

    def test_txt_extension_blocked(self, patch_workspace: Path) -> None:
        with pytest.raises(InvalidExtensionError):
            write_json_file("output.txt", {})
