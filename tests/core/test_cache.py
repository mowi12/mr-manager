"""Tests for discovery cache persistence."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from mr_manager.core import cache
from mr_manager.core.cache import load_cached_repositories, save_cached_repositories


@pytest.fixture(autouse=True)
def cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the cache file into a temporary directory."""
    path = tmp_path / "cache" / "discovery_cache.json"
    monkeypatch.setattr(cache, "_cache_file_path", lambda: path)
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Return a discovery root for cache entries."""
    return tmp_path / "root"


class TestRoundTrip:
    """Saving and loading the cache."""

    def test_saved_repositories_are_loaded_back(self, tmp_path: Path, root: Path) -> None:
        repositories = [tmp_path / "alpha", tmp_path / "beta"]

        save_cached_repositories(repositories, root)

        assert load_cached_repositories(root) == repositories

    def test_empty_repository_list_round_trips(self, root: Path) -> None:
        save_cached_repositories([], root)

        assert load_cached_repositories(root) == []

    def test_parent_directory_is_created(self, cache_file: Path, root: Path) -> None:
        save_cached_repositories([], root)

        assert cache_file.exists()

    def test_unwritable_cache_location_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: Path
    ) -> None:
        monkeypatch.setattr(
            Path, "write_text", lambda *_a, **_k: (_ for _ in ()).throw(OSError("read-only"))
        )

        save_cached_repositories([tmp_path / "alpha"], root)  # must not raise


class TestRootKeying:
    """The cache must only be reused for the root that produced it."""

    def test_cache_from_a_different_root_is_a_miss(self, tmp_path: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"], tmp_path / "first")

        assert load_cached_repositories(tmp_path / "second") is None

    def test_equivalent_root_spellings_hit_the_same_entry(self, tmp_path: Path) -> None:
        repositories = [tmp_path / "alpha"]
        save_cached_repositories(repositories, tmp_path / "root")

        assert load_cached_repositories(tmp_path / "." / "root") == repositories

    def test_home_relative_root_is_normalized(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        repositories = [tmp_path / "projects" / "alpha"]
        save_cached_repositories(repositories, Path("~/projects"))

        assert load_cached_repositories(tmp_path / "projects") == repositories


class TestCacheMisses:
    """Conditions that must be treated as a cache miss rather than an error."""

    def test_absent_file_is_a_miss(self, root: Path) -> None:
        assert load_cached_repositories(root) is None

    def test_corrupt_json_is_a_miss(self, cache_file: Path, root: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("{not json", encoding="utf-8")

        assert load_cached_repositories(root) is None

    def test_legacy_bare_list_format_is_a_miss(self, cache_file: Path, root: Path) -> None:
        # Written by versions that cached a bare list with no discovery root.
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps(["/a", "/b"]), encoding="utf-8")

        assert load_cached_repositories(root) is None

    def test_unknown_schema_version_is_a_miss(self, cache_file: Path, root: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({"version": 99, "root": str(root), "repositories": []}), encoding="utf-8"
        )

        assert load_cached_repositories(root) is None

    def test_malformed_repository_list_is_a_miss(self, cache_file: Path, root: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({"version": 1, "root": cache._normalize_root(root), "repositories": "x"}),
            encoding="utf-8",
        )

        assert load_cached_repositories(root) is None

    def test_non_string_entries_are_dropped(self, cache_file: Path, root: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "root": cache._normalize_root(root),
                    "saved_at": time.time(),
                    "repositories": ["/a", 5, None, "/b"],
                }
            ),
            encoding="utf-8",
        )

        assert load_cached_repositories(root) == [Path("/a"), Path("/b")]


class TestExpiration:
    """TTL handling."""

    def test_fresh_cache_is_returned(self, tmp_path: Path, root: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"], root)

        assert load_cached_repositories(root, cache_ttl_hours=24) == [tmp_path / "alpha"]

    def test_expired_cache_is_a_miss(self, cache_file: Path, tmp_path: Path, root: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"], root)
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        payload["saved_at"] = time.time() - (25 * 3600)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        assert load_cached_repositories(root, cache_ttl_hours=24) is None

    def test_missing_timestamp_falls_back_to_file_mtime(
        self, cache_file: Path, tmp_path: Path, root: Path
    ) -> None:
        save_cached_repositories([tmp_path / "alpha"], root)
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        del payload["saved_at"]
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
        stale = time.time() - (25 * 3600)
        os.utime(cache_file, (stale, stale))

        assert load_cached_repositories(root, cache_ttl_hours=24) is None

    @pytest.mark.parametrize("ttl_hours", [0, -1])
    def test_non_positive_ttl_is_rejected(self, ttl_hours: int, root: Path) -> None:
        with pytest.raises(ValueError, match="cache_ttl_hours must be greater than 0"):
            load_cached_repositories(root, cache_ttl_hours=ttl_hours)
