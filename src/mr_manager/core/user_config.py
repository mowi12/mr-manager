"""User configuration loading and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_DISCOVERY_CACHE_TTL_HOURS = 24
_DEFAULT_DISCOVERY_ROOT = Path.home()
_USER_CONFIG_PATH = Path.home() / ".config" / "mr-manager" / "config.yaml"


@dataclass(frozen=True)
class UserConfig:
    """Configurable user settings for mr-manager behavior."""

    discovery_cache_ttl_hours: int = DEFAULT_DISCOVERY_CACHE_TTL_HOURS
    discovery_root: Path = _DEFAULT_DISCOVERY_ROOT


def get_user_config_path() -> Path:
    """Return the canonical user config file path."""
    return _USER_CONFIG_PATH


def get_default_user_config() -> UserConfig:
    """Return default user settings used when config file is absent."""
    return UserConfig(
        discovery_cache_ttl_hours=DEFAULT_DISCOVERY_CACHE_TTL_HOURS,
        discovery_root=_DEFAULT_DISCOVERY_ROOT,
    )


def _strip_yaml_quotes(value: str) -> str:
    """Strip surrounding YAML-like quotes from a scalar string value."""
    if len(value) < 2:
        return value
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"')
    return value


def _parse_user_config_yaml(content: str) -> dict[str, str]:
    """Parse a minimal YAML subset used by the user config file."""
    parsed_values: dict[str, str] = {}
    active_section: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line.startswith("  "):
            if active_section is None:
                msg = "Nested config key found before a section header."
                raise ValueError(msg)
            if ":" not in stripped:
                msg = f"Invalid config line: {raw_line}"
                raise ValueError(msg)
            nested_key, nested_value = stripped.split(":", maxsplit=1)
            parsed_values[f"{active_section}.{nested_key.strip()}"] = _strip_yaml_quotes(
                nested_value.strip()
            )
            continue

        if stripped.endswith(":"):
            active_section = stripped[:-1].strip()
            continue

        if ":" not in stripped:
            msg = f"Invalid config line: {raw_line}"
            raise ValueError(msg)
        key, value = stripped.split(":", maxsplit=1)
        parsed_values[key.strip()] = _strip_yaml_quotes(value.strip())
        active_section = None

    return parsed_values


def _validate_discovery_cache_ttl_hours(value: str | None, *, key_name: str) -> int:
    """Validate and normalize configured cache TTL in hours."""
    if value is None or value == "":
        return DEFAULT_DISCOVERY_CACHE_TTL_HOURS
    try:
        ttl_hours = int(value)
    except ValueError as error:
        msg = f"Invalid {key_name} value: {value!r}"
        raise ValueError(msg) from error
    if ttl_hours <= 0:
        msg = f"{key_name} must be greater than 0."
        raise ValueError(msg)
    return ttl_hours


def _resolve_cache_ttl_hours(parsed_values: dict[str, str]) -> int:
    """Resolve configured cache TTL from the hours-based config key."""
    if "discovery.cache_ttl_seconds" in parsed_values:
        msg = "Unsupported key discovery.cache_ttl_seconds. Use discovery.cache_ttl_hours."
        raise ValueError(msg)
    return _validate_discovery_cache_ttl_hours(
        parsed_values.get("discovery.cache_ttl_hours"),
        key_name="discovery.cache_ttl_hours",
    )


def _validate_discovery_root(value: str | None) -> Path:
    """Validate and normalize the configured discovery root path."""
    if value is None or value == "":
        return _DEFAULT_DISCOVERY_ROOT
    return Path(value).expanduser().resolve(strict=False)


def load_user_config(config_path: Path | None = None) -> UserConfig:
    """Load user settings from disk, or defaults when file is missing.

    Args:
        config_path: Optional override for the config file location.

    Returns:
        Parsed user settings.

    Raises:
        ValueError: Config content is syntactically invalid or has invalid values.
        OSError: Config file cannot be read.
    """
    resolved_config_path = config_path or get_user_config_path()
    if not resolved_config_path.exists():
        return get_default_user_config()

    parsed_values = _parse_user_config_yaml(resolved_config_path.read_text(encoding="utf-8"))
    return UserConfig(
        discovery_cache_ttl_hours=_resolve_cache_ttl_hours(parsed_values),
        discovery_root=_validate_discovery_root(parsed_values.get("discovery.root")),
    )


def _single_quote_yaml_string(value: str) -> str:
    """Return a single-quoted YAML scalar string."""
    return "'" + value.replace("'", "''") + "'"


def save_user_config(config: UserConfig, config_path: Path | None = None) -> None:
    """Persist user settings to disk.

    Args:
        config: Settings to write.
        config_path: Optional override for the config file location.

    Raises:
        ValueError: Config values are invalid.
        OSError: Config file cannot be created or written.
    """
    ttl_hours = _validate_discovery_cache_ttl_hours(
        str(config.discovery_cache_ttl_hours),
        key_name="discovery.cache_ttl_hours",
    )
    discovery_root = _validate_discovery_root(str(config.discovery_root))
    resolved_config_path = config_path or get_user_config_path()
    config_text = (
        "discovery:\n"
        f"  cache_ttl_hours: {ttl_hours}\n"
        f"  root: {_single_quote_yaml_string(discovery_root.as_posix())}\n"
    )
    resolved_config_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_config_path.write_text(config_text, encoding="utf-8")
