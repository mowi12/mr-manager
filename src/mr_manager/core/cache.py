"""Cache management for discovered repositories."""

from __future__ import annotations

import json
import time
from pathlib import Path

from mr_manager.core.user_config import DEFAULT_DISCOVERY_CACHE_TTL_HOURS

_CACHE_SCHEMA_VERSION = 1


def _cache_file_path() -> Path:
    """Return the discovery cache file location in the standard user cache directory."""
    return Path.home() / ".cache" / "mr-manager" / "discovery_cache.json"


def _normalize_root(root: Path) -> str:
    """Normalize a discovery root for stable comparison across runs."""
    return root.expanduser().resolve(strict=False).as_posix()


def load_cached_repositories(
    root: Path,
    cache_ttl_hours: int = DEFAULT_DISCOVERY_CACHE_TTL_HOURS,
) -> list[Path] | None:
    """Load repositories cached for a discovery root, when still valid.

    Args:
        root: Discovery root the cached results must belong to.
        cache_ttl_hours: Maximum cache age in hours before expiration.

    Returns:
        List of absolute repository paths, or None when the cache is missing,
        expired, unreadable, written for a different root, or in a format this
        version does not recognize.

    Raises:
        ValueError: cache_ttl_hours is not greater than zero.
    """
    if cache_ttl_hours <= 0:
        msg = "cache_ttl_hours must be greater than 0."
        raise ValueError(msg)

    cache_file = _cache_file_path()
    if not cache_file.exists():
        return None

    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # If the file is unreadable or corrupt, ignore the cache
        return None

    # A bare list is the pre-versioning format, which carried no discovery root.
    # It cannot be validated against the requested root, so treat it as a miss.
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != _CACHE_SCHEMA_VERSION:
        return None
    if payload.get("root") != _normalize_root(root):
        return None

    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        return None

    # Prefer the recorded timestamp so the TTL survives operations that reset mtime.
    saved_at = payload.get("saved_at")
    if not isinstance(saved_at, int | float):
        saved_at = cache_file.stat().st_mtime
    if time.time() - saved_at > cache_ttl_hours * 3600:
        return None

    # Ensure all cached items are valid paths
    return [Path(repo) for repo in repositories if isinstance(repo, str)]


def save_cached_repositories(repositories: list[Path], root: Path) -> None:
    """Save repositories discovered under a root to the cache file.

    Args:
        repositories: List of absolute repository paths to cache.
        root: Discovery root the results were produced from.
    """
    cache_file = _cache_file_path()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = {
            "version": _CACHE_SCHEMA_VERSION,
            "root": _normalize_root(root),
            "saved_at": time.time(),
            "repositories": [str(repo) for repo in repositories],
        }
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # Fail gracefully if we can't write to the cache directory
