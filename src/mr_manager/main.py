"""Application entrypoint for mr-manager."""

import sys
from importlib.metadata import PackageNotFoundError, version

from mr_manager.ui import MrManagerApp


def _get_installed_version() -> str:
    """Return the installed mr-manager version from package metadata."""
    try:
        return version("mr-manager")
    except PackageNotFoundError as exc:
        message = "Unable to determine mr-manager version from installed package metadata."
        raise RuntimeError(message) from exc


def _handle_version_flag(argv: list[str]) -> int | None:
    """Handle the -v flag and return an exit code when handled."""
    if "-v" not in argv:
        return None
    try:
        installed_version = _get_installed_version()
    except RuntimeError as error:
        print("mr-manager unknown")
        print(f"Error: {error}", file=sys.stderr)
        if error.__cause__ is not None:
            print(f"Cause: {error.__cause__}", file=sys.stderr)
        return 1
    print(f"mr-manager {installed_version}")
    return 0


def main() -> None:
    """Run CLI preflight flags or start the mr-manager Textual application."""
    version_exit_code = _handle_version_flag(sys.argv[1:])
    if version_exit_code is not None:
        raise SystemExit(version_exit_code)
    MrManagerApp().run()


if __name__ == "__main__":
    main()
