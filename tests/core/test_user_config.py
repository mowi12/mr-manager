"""Tests for user configuration parsing and persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from mr_manager.core.user_config import (
    DEFAULT_DISCOVERY_CACHE_TTL_HOURS,
    UserConfig,
    _parse_user_config_yaml,
    _resolve_cache_ttl_hours,
    _strip_yaml_quotes,
    _validate_discovery_root,
    load_user_config,
    save_user_config,
)


class TestStripYamlQuotes:
    """Behavior of `_strip_yaml_quotes`."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("plain", "plain"),
            ("'single'", "single"),
            ('"double"', "double"),
            ("'it''s'", "it's"),
            ('"a\\"b"', 'a"b'),
            ("'", "'"),
            ("", ""),
            ("'unterminated", "'unterminated"),
        ],
    )
    def test_quotes_are_stripped(self, raw: str, expected: str) -> None:
        assert _strip_yaml_quotes(raw) == expected


class TestParseUserConfigYaml:
    """Behavior of `_parse_user_config_yaml`."""

    def test_nested_keys_are_flattened_with_their_section(self) -> None:
        parsed = _parse_user_config_yaml("discovery:\n  root_path: /tmp\n  cache_ttl_hours: 6\n")

        assert parsed == {"discovery.root_path": "/tmp", "discovery.cache_ttl_hours": "6"}

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        parsed = _parse_user_config_yaml("# lead\n\ndiscovery:\n  # inner\n  root_path: /tmp\n")

        assert parsed == {"discovery.root_path": "/tmp"}

    def test_top_level_key_resets_the_active_section(self) -> None:
        parsed = _parse_user_config_yaml("discovery:\n  root_path: /tmp\nother: 1\n")

        assert parsed == {"discovery.root_path": "/tmp", "other": "1"}

    def test_values_may_contain_colons(self) -> None:
        parsed = _parse_user_config_yaml("url: https://example.com:8443/x\n")

        assert parsed == {"url": "https://example.com:8443/x"}

    def test_nested_key_before_any_section_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Nested config key found before a section header"):
            _parse_user_config_yaml("  root_path: /tmp\n")

    @pytest.mark.parametrize("content", ["discovery:\n  novalue\n", "novalue\n"])
    def test_lines_without_a_separator_are_rejected(self, content: str) -> None:
        with pytest.raises(ValueError, match="Invalid config line"):
            _parse_user_config_yaml(content)


class TestResolveCacheTtlHours:
    """Behavior of `_resolve_cache_ttl_hours`."""

    def test_missing_key_falls_back_to_the_default(self) -> None:
        assert _resolve_cache_ttl_hours({}) == DEFAULT_DISCOVERY_CACHE_TTL_HOURS

    def test_configured_value_is_used(self) -> None:
        assert _resolve_cache_ttl_hours({"discovery.cache_ttl_hours": "6"}) == 6

    def test_legacy_seconds_key_is_rejected_with_guidance(self) -> None:
        with pytest.raises(ValueError, match="Use discovery.cache_ttl_hours"):
            _resolve_cache_ttl_hours({"discovery.cache_ttl_seconds": "3600"})

    def test_non_integer_value_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid discovery.cache_ttl_hours"):
            _resolve_cache_ttl_hours({"discovery.cache_ttl_hours": "soon"})

    @pytest.mark.parametrize("value", ["0", "-3"])
    def test_non_positive_value_is_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="must be greater than 0"):
            _resolve_cache_ttl_hours({"discovery.cache_ttl_hours": value})


class TestValidateDiscoveryRoot:
    """Behavior of `_validate_discovery_root`."""

    @pytest.mark.parametrize("value", [None, ""])
    def test_absent_value_falls_back_to_home(self, value: str | None) -> None:
        assert _validate_discovery_root(value) == Path.home()

    def test_tilde_is_expanded(self) -> None:
        assert _validate_discovery_root("~/projects") == Path.home() / "projects"


class TestLoadAndSave:
    """Round-tripping the config file."""

    def test_absent_file_yields_defaults(self, tmp_path: Path) -> None:
        config = load_user_config(tmp_path / "absent.yaml")

        assert config.discovery_cache_ttl_hours == DEFAULT_DISCOVERY_CACHE_TTL_HOURS
        assert config.discovery_root == Path.home()

    def test_saved_config_is_loaded_back(self, tmp_path: Path) -> None:
        config_path = tmp_path / "nested" / "config.yaml"
        original = UserConfig(discovery_cache_ttl_hours=6, discovery_root=tmp_path / "projects")

        save_user_config(original, config_path)

        assert load_user_config(config_path) == original

    def test_saving_rejects_an_invalid_ttl(self, tmp_path: Path) -> None:
        config = UserConfig(discovery_cache_ttl_hours=0, discovery_root=tmp_path)

        with pytest.raises(ValueError, match="must be greater than 0"):
            save_user_config(config, tmp_path / "config.yaml")
