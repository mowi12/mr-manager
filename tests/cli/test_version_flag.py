"""Tests for the `-v` command-line flag."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import pytest

from mr_manager.cli import version_flag
from mr_manager.cli.version_flag import handle_version_flag


def test_absent_flag_is_not_handled(capsys: pytest.CaptureFixture[str]) -> None:
    assert handle_version_flag(["mr-manager"]) is None
    assert capsys.readouterr().out == ""


def test_flag_prints_the_installed_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(version_flag, "version", lambda _name: "1.2.3")

    assert handle_version_flag(["mr-manager", "-v"]) == 0
    assert capsys.readouterr().out == "mr-manager 1.2.3\n"


def test_missing_package_metadata_reports_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_flag, "version", _missing)

    assert handle_version_flag(["mr-manager", "-v"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "mr-manager unknown\n"
    assert "Unable to determine mr-manager version" in captured.err
    assert "\nCause: " in captured.err
