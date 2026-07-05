"""
Unit tests for the write-safety path validator.
Zero mocking — the validator has no external dependencies.
These must all pass before any WRITE handler is built.
"""

from __future__ import annotations

import pytest

from services.action.safety.path_validator import (
    ALLOWED_EXTENSIONS,
    WORKSPACE_ROOT,
    validate_write_target,
)
from shared.exceptions import InvalidExtensionError, PathTraversalError


class TestWorkspaceConstants:
    def test_workspace_root_is_absolute(self) -> None:
        assert WORKSPACE_ROOT.is_absolute()

    def test_workspace_root_ends_with_data_workspace(self) -> None:
        assert WORKSPACE_ROOT.parts[-2:] == ("data", "workspace")

    def test_only_json_allowed(self) -> None:
        assert frozenset({".json"}) == ALLOWED_EXTENSIONS


class TestValidTargets:
    def test_simple_json_file(self) -> None:
        result = validate_write_target("output.json")
        assert result == (WORKSPACE_ROOT / "output.json").resolve()

    def test_subdirectory_json(self) -> None:
        result = validate_write_target("tickets/update.json")
        assert result.suffix == ".json"
        assert str(result).startswith(str(WORKSPACE_ROOT))


class TestPathTraversalBlocked:
    def test_dotdot_escape(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_write_target("../../etc/passwd.json")

    def test_absolute_path_blocked(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_write_target("/etc/passwd.json")

    def test_empty_string_blocked(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_write_target("")

    def test_whitespace_only_blocked(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_write_target("   ")


class TestExtensionAllowlist:
    def test_txt_blocked(self) -> None:
        with pytest.raises(InvalidExtensionError):
            validate_write_target("output.txt")

    def test_py_blocked(self) -> None:
        with pytest.raises(InvalidExtensionError):
            validate_write_target("exploit.py")

    def test_no_extension_blocked(self) -> None:
        with pytest.raises(InvalidExtensionError):
            validate_write_target("noextension")

    def test_csv_blocked(self) -> None:
        with pytest.raises(InvalidExtensionError):
            validate_write_target("data.csv")
