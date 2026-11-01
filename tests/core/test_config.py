"""Tests for myrepos configuration parsing and update helpers."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from mr_manager.core.config import (
    _build_repo_block,
    _format_section_name,
    _remove_sections_by_name,
    _resolve_clone_source,
    _shell_single_quote,
    parse_configured_repo_sections,
    write_config_updates,
)


class TestParseConfiguredRepoSections:
    """Behavior of `parse_configured_repo_sections`."""

    def test_missing_file_returns_empty_mapping(self, tmp_path: Path) -> None:
        assert parse_configured_repo_sections(tmp_path / "absent.mrconfig") == {}

    def test_relative_section_resolves_against_config_directory(self, tmp_path: Path) -> None:
        config_path = tmp_path / "cfg" / ".mrconfig"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("[projects/alpha]\ncheckout = true\n", encoding="utf-8")

        configured = parse_configured_repo_sections(config_path)

        assert configured == {config_path.parent / "projects" / "alpha": ["projects/alpha"]}

    def test_absolute_section_is_preserved(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        repo = tmp_path / "beta"
        config_path.write_text(f"[{repo}]\n", encoding="utf-8")

        assert parse_configured_repo_sections(config_path) == {repo: [str(repo)]}

    def test_tilde_section_is_expanded(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[~/gamma]\n", encoding="utf-8")

        assert parse_configured_repo_sections(config_path) == {Path.home() / "gamma": ["~/gamma"]}

    def test_default_section_is_skipped(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[DEFAULT]\njobs = 4\n\n[alpha]\n", encoding="utf-8")

        assert list(parse_configured_repo_sections(config_path)) == [tmp_path / "alpha"]

    @pytest.mark.parametrize("name", ["default", "Default"])
    def test_only_the_exact_default_name_is_special(self, tmp_path: Path, name: str) -> None:
        # mr compares the section name to `DEFAULT` case-sensitively, so `[default]` is a
        # regular repository section for a directory named `default`.
        config_path = tmp_path / ".mrconfig"
        config_path.write_text(f"[{name}]\n", encoding="utf-8")

        assert parse_configured_repo_sections(config_path) == {tmp_path / name: [name]}

    def test_distinct_names_for_same_path_are_collected_together(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text(f"[alpha]\n[{tmp_path / 'alpha'}]\n", encoding="utf-8")

        configured = parse_configured_repo_sections(config_path)

        assert configured == {tmp_path / "alpha": ["alpha", str(tmp_path / "alpha")]}

    def test_trailing_whitespace_after_a_header_is_allowed(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[alpha]   \n", encoding="utf-8")

        assert parse_configured_repo_sections(config_path) == {tmp_path / "alpha": ["alpha"]}

    def test_indented_bracket_line_is_a_continuation_not_a_header(self, tmp_path: Path) -> None:
        # mr treats indented lines as continuations of the previous value; only lines
        # starting with `[` in the first column open a section.
        config_path = tmp_path / ".mrconfig"
        config_path.write_text(
            "[alpha]\ncheckout =\n  [ -d x ]\n  git clone u alpha\n[beta]\n", encoding="utf-8"
        )

        assert list(parse_configured_repo_sections(config_path)) == [
            tmp_path / "alpha",
            tmp_path / "beta",
        ]


class TestRemoveSectionsByName:
    """Behavior of `_remove_sections_by_name`."""

    @staticmethod
    def _lines(text: str) -> list[str]:
        return text.splitlines(keepends=True)

    def test_empty_removal_set_returns_input_unchanged(self) -> None:
        lines = self._lines("[alpha]\ncheckout = true\n")

        assert _remove_sections_by_name(lines, set()) == lines

    def test_section_body_is_removed_up_to_next_header(self) -> None:
        lines = self._lines("[alpha]\ncheckout = a\nupdate = b\n[beta]\ncheckout = c\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "[beta]\ncheckout = c\n"

    def test_final_section_is_removed_through_end_of_file(self) -> None:
        lines = self._lines("[alpha]\ncheckout = a\n[beta]\ncheckout = b\nupdate = c\n")

        remaining = _remove_sections_by_name(lines, {"beta"})

        assert "".join(remaining) == "[alpha]\ncheckout = a\n"

    def test_unknown_section_name_is_a_no_op(self) -> None:
        lines = self._lines("[alpha]\ncheckout = a\n")

        assert _remove_sections_by_name(lines, {"missing"}) == lines

    def test_removing_the_only_section_empties_the_file(self) -> None:
        lines = self._lines("[alpha]\ncheckout = a\n")

        assert _remove_sections_by_name(lines, {"alpha"}) == []

    def test_preamble_before_first_header_is_preserved(self) -> None:
        lines = self._lines("# comment\n\n[alpha]\ncheckout = a\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "# comment\n\n"

    def test_multiple_sections_are_removed_together(self) -> None:
        lines = self._lines("[alpha]\na = 1\n[beta]\nb = 2\n[gamma]\nc = 3\n")

        remaining = _remove_sections_by_name(lines, {"alpha", "gamma"})

        assert "".join(remaining) == "[beta]\nb = 2\n"

    def test_continuation_lines_are_removed_with_their_section(self) -> None:
        lines = self._lines("[alpha]\ncheckout =\n  [ -d x ]\n  git clone u alpha\n[beta]\nb = 2\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "[beta]\nb = 2\n"

    def test_comment_preceding_the_next_header_is_preserved(self) -> None:
        lines = self._lines("[alpha]\na = 1\n\n# notes about beta\n[beta]\nb = 2\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "# notes about beta\n[beta]\nb = 2\n"

    def test_commented_option_ending_a_section_is_removed_with_it(self) -> None:
        lines = self._lines("[alpha]\na = 1\n# update = x\n\n[beta]\nb = 2\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "[beta]\nb = 2\n"

    def test_comment_without_blank_line_separation_is_removed_with_the_section(self) -> None:
        # Nothing marks where alpha ends, so the comment is treated as part of alpha.
        lines = self._lines("[alpha]\na = 1\n# update = x\n[beta]\nb = 2\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "[beta]\nb = 2\n"

    def test_comment_inside_a_section_body_is_removed_with_it(self) -> None:
        lines = self._lines("[alpha]\n# disabled\na = 1\n[beta]\nb = 2\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "[beta]\nb = 2\n"

    def test_blank_lines_between_sections_are_removed_with_the_section(self) -> None:
        lines = self._lines("[alpha]\na = 1\n\n[beta]\nb = 2\n")

        remaining = _remove_sections_by_name(lines, {"alpha"})

        assert "".join(remaining) == "[beta]\nb = 2\n"


class TestShellSingleQuote:
    """Behavior of `_shell_single_quote`."""

    @pytest.mark.parametrize(
        "value",
        [
            "plain",
            "with space",
            "O'Brien",
            "it's a 'quoted' value",
            'double"quote',
            "semi; rm -rf /",
            "$(whoami)",
            "back\\slash",
        ],
    )
    def test_quoted_value_round_trips_through_a_shell_parser(self, value: str) -> None:
        assert shlex.split(_shell_single_quote(value)) == [value]


class TestFormatSectionName:
    """Behavior of `_format_section_name`."""

    def test_repo_under_config_directory_becomes_relative(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"

        assert _format_section_name(config_path, tmp_path / "a" / "b") == "a/b"

    def test_repo_outside_config_directory_stays_absolute(self, tmp_path: Path) -> None:
        config_path = tmp_path / "cfg" / ".mrconfig"
        config_path.parent.mkdir()
        outside = tmp_path / "elsewhere"

        assert _format_section_name(config_path, outside) == outside.resolve().as_posix()


class TestResolveCloneSource:
    """Behavior of `_resolve_clone_source`."""

    def test_origin_remote_is_preferred(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        repo = make_real_git_repo(tmp_path / "repo", origin="https://example.com/x.git")

        assert _resolve_clone_source(repo) == "https://example.com/x.git"

    def test_repository_path_is_used_without_an_origin(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        repo = make_real_git_repo(tmp_path / "repo")

        assert _resolve_clone_source(repo) == repo.resolve().as_posix()

    def test_missing_git_executable_raises_runtime_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", _raise)

        with pytest.raises(RuntimeError, match="git executable not found"):
            _resolve_clone_source(tmp_path)


class TestBuildRepoBlock:
    """Behavior of `_build_repo_block`."""

    def test_block_contains_section_header_and_checkout_command(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        config_path = tmp_path / ".mrconfig"
        repo = make_real_git_repo(tmp_path / "alpha", origin="https://example.com/a.git")

        block = _build_repo_block(config_path, repo)

        assert block == "[alpha]\ncheckout = git clone 'https://example.com/a.git' 'alpha'"


class TestWriteConfigUpdates:
    """Behavior of `write_config_updates`."""

    def test_additions_to_an_absent_file_create_it(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        config_path = tmp_path / "nested" / ".mrconfig"
        repo = make_real_git_repo(tmp_path / "alpha", origin="https://example.com/a.git")

        write_config_updates(config_path, [repo], set())

        # The repo sits outside the config directory, so the section name stays absolute:
        # `relative_to` does not walk upward into `../`.
        assert config_path.read_text(encoding="utf-8") == (
            f"[{repo.resolve().as_posix()}]\n"
            "checkout = git clone 'https://example.com/a.git' 'alpha'\n"
        )

    def test_additions_are_appended_after_preserved_content(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[existing]\ncheckout = true\n", encoding="utf-8")
        repo = make_real_git_repo(tmp_path / "alpha", origin="https://example.com/a.git")

        write_config_updates(config_path, [repo], set())

        assert config_path.read_text(encoding="utf-8") == (
            "[existing]\ncheckout = true\n"
            "\n"
            "[alpha]\ncheckout = git clone 'https://example.com/a.git' 'alpha'\n"
        )

    def test_multiple_additions_are_separated_by_a_blank_line(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        config_path = tmp_path / ".mrconfig"
        first = make_real_git_repo(tmp_path / "alpha", origin="https://example.com/a.git")
        second = make_real_git_repo(tmp_path / "beta", origin="https://example.com/b.git")

        write_config_updates(config_path, [first, second], set())

        assert config_path.read_text(encoding="utf-8") == (
            "[alpha]\ncheckout = git clone 'https://example.com/a.git' 'alpha'\n"
            "\n"
            "[beta]\ncheckout = git clone 'https://example.com/b.git' 'beta'\n"
        )

    def test_removal_only_rewrites_remaining_sections(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[alpha]\na = 1\n[beta]\nb = 2\n", encoding="utf-8")

        write_config_updates(config_path, [], {"alpha"})

        assert config_path.read_text(encoding="utf-8") == "[beta]\nb = 2\n"

    def test_combined_add_and_remove_are_applied(
        self, tmp_path: Path, make_real_git_repo: Callable[..., Path]
    ) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[alpha]\na = 1\n[beta]\nb = 2\n", encoding="utf-8")
        repo = make_real_git_repo(tmp_path / "gamma", origin="https://example.com/g.git")

        write_config_updates(config_path, [repo], {"alpha"})

        assert config_path.read_text(encoding="utf-8") == (
            "[beta]\nb = 2\n\n[gamma]\ncheckout = git clone 'https://example.com/g.git' 'gamma'\n"
        )

    def test_removing_every_section_writes_an_empty_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[alpha]\na = 1\n", encoding="utf-8")

        write_config_updates(config_path, [], {"alpha"})

        assert config_path.read_text(encoding="utf-8") == ""

    def test_trailing_whitespace_is_normalized(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".mrconfig"
        config_path.write_text("[alpha]\na = 1\n\n\n\n", encoding="utf-8")

        write_config_updates(config_path, [], set())

        assert config_path.read_text(encoding="utf-8") == "[alpha]\na = 1\n"
