"""Application entrypoint for mr-manager."""

import sys

from mr_manager.cli import handle_version_flag
from mr_manager.ui import MrManagerApp


def main() -> None:
    """Run CLI preflight flags or start the mr-manager Textual application."""
    version_exit_code = handle_version_flag(sys.argv[1:])
    if version_exit_code is not None:
        raise SystemExit(version_exit_code)
    MrManagerApp().run()


if __name__ == "__main__":
    main()
