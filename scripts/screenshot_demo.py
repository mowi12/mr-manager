"""Run mr-manager against mocked data, e.g. for README screenshots.

Nothing on disk is read or written: repository discovery, the myrepos config,
the discovery cache and the user config are all replaced with in-memory fakes.

Usage:
    uv run python scripts/screenshot_demo.py                       # interactive TUI
    uv run python scripts/screenshot_demo.py --screenshot demo.svg  # headless SVG export
    uv run python scripts/screenshot_demo.py --screenshot demo.svg --size 120x32
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from unittest import mock

from mr_manager.core.user_config import UserConfig
from mr_manager.ui import MrManagerApp

DEMO_HOME = Path("/Users/moritz")

# Repositories "found" by the discovery scan (relative to DEMO_HOME).
DISCOVERED_REPOS = [
    "experiments/data-pipeline",
    "experiments/dev-environment",
    "experiments/ml-models",
    "experiments/scripts",
    "open-source/cli-tools",
    "open-source/component-library",
    "open-source/docs-site",
    "open-source/shared-utils",
    "projects/frontend-app",
    "projects/landing-page",
    "projects/mobile-app",
    "projects/web-client",
    "work/api-service",
    "work/auth-backend",
    "work/infrastructure",
    "work/payment-gateway",
]

# Section names in the fake ~/.mrconfig. Entries not in DISCOVERED_REPOS show up as missing.
CONFIGURED_REPOS = [
    "work/api-service",
    "open-source/docs-site",
    "open-source/shared-utils",
    "open-source/cli-tools",
    "work/archived-service",
    "projects/temp-hackathon",
    "experiments/old-experiments",
    "open-source/deprecated-tool",
]

_CONTROLLER = "mr_manager.ui.selection.controller"
_APP = "mr_manager.ui.app"


def _discovered() -> list[Path]:
    return sorted(DEMO_HOME / repo for repo in DISCOVERED_REPOS)


def _configured() -> dict[Path, list[str]]:
    return {DEMO_HOME / name: [name] for name in CONFIGURED_REPOS}


def apply_demo_patches() -> None:
    """Replace all filesystem-touching functions with in-memory fakes."""
    patches = {
        f"{_CONTROLLER}.discover_git_repositories": lambda _root: _discovered(),
        f"{_CONTROLLER}.parse_configured_repo_sections": lambda _path: _configured(),
        f"{_CONTROLLER}.write_config_updates": lambda *_args, **_kwargs: None,
        f"{_CONTROLLER}.load_cached_repositories": lambda *_args, **_kwargs: None,
        f"{_CONTROLLER}.save_cached_repositories": lambda *_args, **_kwargs: None,
        f"{_CONTROLLER}.load_user_config": lambda: UserConfig(discovery_root=DEMO_HOME),
        f"{_APP}.save_user_config": lambda *_args, **_kwargs: None,
    }
    for target, fake in patches.items():
        mock.patch(target, side_effect=fake).start()


def build_app() -> MrManagerApp:
    """Create the app with its model pointing at the demo home directory."""
    app = MrManagerApp()
    model = app._controller.model
    model.discover_root = DEMO_HOME
    model.config_path = DEMO_HOME / ".mrconfig"
    return app


async def save_screenshot(path: Path, size: tuple[int, int]) -> None:
    """Render the app headlessly and export an SVG screenshot."""
    app = build_app()
    async with app.run_test(size=size) as pilot:
        while app._controller.model.loading:
            await pilot.pause(0.05)
        await pilot.pause()
        app.save_screenshot(filename=path.name, path=str(path.parent))


def _parse_size(value: str) -> tuple[int, int]:
    try:
        cols, rows = (int(part) for part in value.lower().split("x"))
    except ValueError as error:
        msg = f"invalid size {value!r}, expected COLSxROWS (e.g. 100x30)"
        raise argparse.ArgumentTypeError(msg) from error
    return cols, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--screenshot",
        type=Path,
        metavar="PATH",
        help="render headlessly and save an SVG screenshot to PATH instead of running the TUI",
    )
    parser.add_argument(
        "--size",
        type=_parse_size,
        default=(100, 30),
        metavar="COLSxROWS",
        help="terminal size for --screenshot (default: 100x30)",
    )
    args = parser.parse_args()

    apply_demo_patches()
    if args.screenshot:
        asyncio.run(save_screenshot(args.screenshot.resolve(), args.size))
        print(f"Saved screenshot to {args.screenshot}")
    else:
        build_app().run()


if __name__ == "__main__":
    main()
