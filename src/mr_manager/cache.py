"""Cache management for discovered repositories."""

from __future__ import annotations

import json
import time
from pathlib import Path

# Use the standard user cache directory
_CACHE_FILE = Path.home() / ".cache" / "mr-manager" / "discovery_cache.json"
_CACHE_TTL_SECONDS = 86400  # 24 hours


def load_cached_repositories() -> list[Path] | None:
    """Load repositories from cache if the cache is valid and not expired.

    Returns:
        List of absolute repository paths, or None if cache is missing/expired.
    """
    if not _CACHE_FILE.exists():
        return None

    # Check expiration (Time-To-Live)
    file_age = time.time() - _CACHE_FILE.stat().st_mtime
    if file_age > _CACHE_TTL_SECONDS:
        return None

    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        # Ensure all cached items are valid paths
        return [Path(p) for p in data if isinstance(p, str)]
    except (OSError, json.JSONDecodeError):
        # If the file is unreadable or corrupt, ignore the cache
        return None


def save_cached_repositories(repositories: list[Path]) -> None:
    """Save a list of repositories to the cache file.

    Args:
        repositories: List of absolute repository paths to cache.
    """
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = [str(repo) for repo in repositories]
        _CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # Fail gracefully if we can't write to the cache directory
