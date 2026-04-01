# mr-manager Wiki

Welcome to the project wiki for `mr-manager`.

`mr-manager` is a [Textual](https://textual.textualize.io/) TUI that helps you manage repository sections in your
`~/.mrconfig` [myrepos](https://myrepos.branchable.com/) file by scanning local Git repositories and letting you
toggle which ones should be tracked.

## Start here

- [Contribution Guidelines](https://github.com/mowi12/mr-manager/wiki/Contribution-Guidelines)
- [Troubleshooting](https://github.com/mowi12/mr-manager/wiki/Troubleshooting)
- [Release Process](https://github.com/mowi12/mr-manager/wiki/Release-Process)

## What the app does

- Scans your home directory for Git repositories (results are cached for 24 hours).
- Reads existing configured repos from `~/.mrconfig`.
- Lets you toggle repositories with keyboard controls.
- Writes add/remove changes back to `~/.mrconfig`.

## Keybindings

- `space`: Toggle selected repository
- `j`: Move down
- `k`: Move up
- `s`: Save changes
- `r`: Refresh repository scan (bypasses cache)
- `q`: Quit (with unsaved-changes confirmation when needed)

## Installation

| Channel       | Command                   |
|---------------|---------------------------|
| Python (pipx) | `pipx install mr-manager` |

See the [README](https://github.com/mowi12/mr-manager#installation) for full installation instructions per channel.

## Performance Tracking

`mr-manager` tracks performance via a benchmarking script (`scripts/benchmark.py`).
It compares total startup time and "time-per-repository" efficiency across Git versions
to ensure performance stays optimal.

The script supports:

- Local benchmarking with persisted text and graph artifacts
- CI-friendly benchmarking with text-only output (`--steps collect,summary`)
- Step-based runs (`collect`, `summary`, `plot`) to reuse prior collected data
