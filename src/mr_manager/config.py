"""myrepos configuration parsing and update helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SECTION_HEADER_PATTERN = re.compile(r"^\s*\[([^]]+)]\s*$")


def _normalize_repo_reference(config_path: Path, repo_reference: str) -> Path:
    """Normalize a repository reference from config into an absolute path.

    Args:
        config_path: Path to the myrepos config file.
        repo_reference: Section header value from config.

    Returns:
        Absolute normalized repository path.
    """
    reference_path = Path(repo_reference).expanduser()
    if reference_path.is_absolute():
        return reference_path.resolve(strict=False)
    return (config_path.parent / reference_path).resolve(strict=False)


def parse_configured_repo_sections(config_path: Path) -> dict[Path, list[str]]:
    """Parse repository section headers from a myrepos config file.

    Args:
        config_path: Path to the myrepos config file.

    Returns:
        Mapping of normalized repository path to original section names.
    """
    if not config_path.exists():
        return {}

    configured: dict[Path, list[str]] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        match = _SECTION_HEADER_PATTERN.match(line)
        if not match:
            continue
        section_name = match.group(1).strip()
        if section_name.upper() == "DEFAULT":
            continue
        normalized_path = _normalize_repo_reference(config_path, section_name)
        configured.setdefault(normalized_path, []).append(section_name)
    return configured


def _remove_sections_by_name(lines: list[str], section_names_to_remove: set[str]) -> list[str]:
    """Remove named section blocks from config text lines.

    Args:
        lines: Config file lines including newline characters when available.
        section_names_to_remove: Section names that should be removed fully.

    Returns:
        Updated list of config lines with matching sections removed.
    """
    if not section_names_to_remove:
        return lines

    section_ranges: list[tuple[str, int, int]] = []
    section_starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        match = _SECTION_HEADER_PATTERN.match(line.strip())
        if match:
            section_starts.append((match.group(1).strip(), index))

    for index, (section_name, start) in enumerate(section_starts):
        end = section_starts[index + 1][1] if index + 1 < len(section_starts) else len(lines)
        section_ranges.append((section_name, start, end))

    updated_lines = lines.copy()
    for section_name, start, end in reversed(section_ranges):
        if section_name in section_names_to_remove:
            del updated_lines[start:end]

    return updated_lines


def _shell_single_quote(value: str) -> str:
    """Return a shell-safe single-quoted string.

    Args:
        value: Raw string value to quote.

    Returns:
        Single-quoted shell-safe representation.
    """
    escaped_value = value.replace("'", "'\"'\"'")
    return f"'{escaped_value}'"


def _format_section_name(config_path: Path, repo_path: Path) -> str:
    """Format a repository path into mr section style.

    Args:
        config_path: Path to the myrepos config file.
        repo_path: Absolute repository path.

    Returns:
        Path relative to config directory when possible, otherwise absolute path.
    """
    config_dir = config_path.parent.resolve(strict=False)
    resolved_repo_path = repo_path.resolve(strict=False)
    try:
        return resolved_repo_path.relative_to(config_dir).as_posix()
    except ValueError:
        return resolved_repo_path.as_posix()


def _resolve_clone_source(repo_path: Path) -> str:
    """Resolve clone source for a repository checkout command.

    Args:
        repo_path: Repository path on disk.

    Returns:
        Remote origin URL when available, otherwise local repository path.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        msg = "git executable not found while resolving repository clone source."
        raise RuntimeError(msg) from error

    origin_url = result.stdout.strip()
    if origin_url:
        return origin_url
    return repo_path.resolve(strict=False).as_posix()


def _build_repo_block(config_path: Path, repo_path: Path) -> str:
    """Build a myrepos section block for one repository.

    Args:
        config_path: Path to the myrepos config file.
        repo_path: Repository path to represent in config.

    Returns:
        Section block with `[path]` and `checkout = git clone ...`.
    """
    section_name = _format_section_name(config_path, repo_path)
    clone_source = _resolve_clone_source(repo_path)
    checkout_target = repo_path.name
    checkout_command = (
        f"checkout = git clone {_shell_single_quote(clone_source)} "
        f"{_shell_single_quote(checkout_target)}"
    )
    return f"[{section_name}]\n{checkout_command}"


def write_config_updates(
    config_path: Path,
    repos_to_add: list[Path],
    section_names_to_remove: set[str],
) -> None:
    """Apply add/remove updates to the myrepos config file.

    Args:
        config_path: Path to the myrepos config file.
        repos_to_add: Repository paths to append in `[path]` + `checkout` block style.
        section_names_to_remove: Original section names to remove fully with their body lines.
    """
    existing_lines = (
        config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        if config_path.exists()
        else []
    )
    preserved_lines = _remove_sections_by_name(existing_lines, section_names_to_remove)
    preserved_text = "".join(preserved_lines).rstrip()
    additions_text = "\n\n".join(_build_repo_block(config_path, repo) for repo in repos_to_add)

    if preserved_text and additions_text:
        updated_text = f"{preserved_text}\n\n{additions_text}\n"
    elif preserved_text:
        updated_text = f"{preserved_text}\n"
    elif additions_text:
        updated_text = f"{additions_text}\n"
    else:
        updated_text = ""

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(updated_text, encoding="utf-8")
