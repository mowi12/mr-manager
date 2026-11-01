"""Cache management for discovered repositories."""

from __future__ import annotations

import json
import time
from pathlib import Path

from mr_manager.core.user_config import DEFAULT_DISCOVERY_CACHE_TTL_HOURS

# Use the standard user cache directory
_CACHE_FILE = Path.home() / ".cache" / "mr-manager" / "discovery_cache.json"
_CACHE_SCHEMA_VERSION = 1


def _normalize_root(root: Path) -> str:
    """Normalize a discovery root so equivalent spellings compare equal."""
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
        List of absolute repository paths, or None when the cache is missing, expired,
        unreadable, written for a different root, or in an unrecognized format.

    Raises:
        ValueError: cache_ttl_hours is not greater than zero.
    """
    if cache_ttl_hours <= 0:
        msg = "cache_ttl_hours must be greater than 0."
        raise ValueError(msg)

    if not _CACHE_FILE.exists():
        return None

    # Check expiration (Time-To-Live)
    file_age = time.time() - _CACHE_FILE.stat().st_mtime
    if file_age > cache_ttl_hours * 3600:
        return None

    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # If the file is unreadable or corrupt, ignore the cache
        return None

    # Anything but the current envelope is unusable, including valid JSON of the wrong
    # shape and the earlier bare-list format, which did not record the discovery root.
    if not isinstance(data, dict) or data.get("version") != _CACHE_SCHEMA_VERSION:
        return None
    if data.get("root") != _normalize_root(root):
        return None
    repositories = data.get("repositories")
    if not isinstance(repositories, list):
        return None
    # Ensure all cached items are valid paths
    return [Path(p) for p in repositories if isinstance(p, str)]


def save_cached_repositories(repositories: list[Path], root: Path) -> None:
    """Save repositories discovered under a root to the cache file.

    Args:
        repositories: List of absolute repository paths to cache.
        root: Discovery root the repositories were discovered under.
    """
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": _CACHE_SCHEMA_VERSION,
            "root": _normalize_root(root),
            "repositories": [str(repo) for repo in repositories],
        }
        _CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # Fail gracefully if we can't write to the cache directory
