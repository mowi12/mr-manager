# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.2] - 2026-11-01

### Fixed

- Indented lines in `.mrconfig` are no longer mistaken for section headers. An indented continuation line such as
  `[ -d x ] || ...` previously split its section, and removing that section left orphaned lines behind.
- Removing a repository no longer deletes the comment block written directly above the next section.
- `[default]` sections are listed as repositories again; only the exact `[DEFAULT]` section is skipped, as in `mr`.
- A discovery cache file containing valid JSON of the wrong shape no longer crashes startup.
- A read-only cache directory no longer raises an error during discovery.
- Git worktrees, which mark their checkout with a `.git` file instead of a directory, are now discovered.
- Changing `discovery.root_path` in the config file no longer shows the previous root's repositories until the cache
  expires.

## [1.0.1] - 2026-05-10

### Fixed

- Configuration field `discovery.root` reverted back to `discovery.root_path`.
- Configuration element order restored to original (root_path, cache_ttl_hours).
- Removed unnecessary quotes from configuration file string values.

## [1.0.0] - 2026-04-27

### Added

- Introduced a user configuration system with persistent config file support at `~/.config/mr-manager/config.yaml`.
- Added interactive configuration editor accessible via a `c` keyboard shortcut.

### Changed

- Discovery cache TTL is now user-configurable.
- Repository discovery root directory can now be customized.

## [0.0.3] - 2026-04-09

### Added

- Added support for `mr-manager -v` to print the installed version and exit.
- Added `ESC` keybinding to trigger the quit flow (including unsaved-changes confirmation).

## [0.0.2] - 2026-04-01

### Added

- Discovered repositories are now cached for 24 hours to ensure instant startup.
- Added `r` keybinding to manually trigger a fresh filesystem scan and update the cache.

## [0.0.1] - 2026-03-26

### Added

- Initial TUI-based CLI application for managing myrepos (`.mrconfig`) file.
- Interactive repository discovery with filesystem scanning for git repositories.
- Visual repository selection interface with toggleable bullet indicators.
- Config file parsing and section normalization for various path formats.
- Unsaved changes detection and confirmation dialogs.

[unreleased]: https://github.com/mowi12/mr-manager/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/mowi12/mr-manager/releases/tag/v1.0.2
[1.0.1]: https://github.com/mowi12/mr-manager/releases/tag/v1.0.1
[1.0.0]: https://github.com/mowi12/mr-manager/releases/tag/v1.0.0
[0.0.3]: https://github.com/mowi12/mr-manager/releases/tag/v0.0.3
[0.0.2]: https://github.com/mowi12/mr-manager/releases/tag/v0.0.2
[0.0.1]: https://github.com/mowi12/mr-manager/releases/tag/v0.0.1
