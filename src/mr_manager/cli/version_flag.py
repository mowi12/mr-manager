"""Version-flag helpers for the mr-manager CLI entrypoint."""

import sys
from importlib.metadata import PackageNotFoundError, version


def get_installed_version() -> str:
    """Return the installed mr-manager version from package metadata."""
    try:
        return version("mr-manager")
    except PackageNotFoundError as exc:
        message = "Unable to determine mr-manager version from installed package metadata."
        raise RuntimeError(message) from exc


def handle_version_flag(argv: list[str]) -> int | None:
    """Handle the -v flag and return an exit code when handled."""
    if "-v" not in argv:
        return None
    try:
        installed_version = get_installed_version()
    except RuntimeError as error:
        print("mr-manager unknown")
        print(f"Error: {error}", file=sys.stderr)
        if error.__cause__ is not None:
            print(f"Cause: {error.__cause__}", file=sys.stderr)
        return 1
    print(f"mr-manager {installed_version}")
    return 0
