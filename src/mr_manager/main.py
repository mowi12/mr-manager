"""Application entrypoint for mr-manager."""

from mr_manager.ui import MrManagerApp


def main() -> None:
    """Start the mr-manager Textual application."""
    MrManagerApp().run()


if __name__ == "__main__":
    main()
