# Contribution Guidelines

Thanks for contributing to `mr-manager`.

## Prerequisites

- Python `>=3.13`
- `uv` package manager
- `git`

## Setup

```bash
uv sync --dev
```

Run the app:

```bash
uv run mr-manager
```

## Quality checks

Before opening a PR, run:

```bash
uv run ruff check --no-fix .
uv run ruff format --check .
uv run ty check
uv run pytest
markdownlint --config markdownlint.json --ignore-path .markdownlintignore "**/*.md"
```

## Tests

Tests live in `tests/`, mirroring the package layout (`tests/core`, `tests/ui`, `tests/cli`). Run them with:

```bash
uv run pytest
```

Every test runs in an isolated environment: `HOME` points to a temporary directory and Git ignores global and system
config, so the suite never reads or writes your real `~/.mrconfig`, discovery cache or user config. Use `tmp_path` for
any files a test needs, and the `make_git_repo` / `make_real_git_repo` fixtures from `tests/conftest.py` for
repositories.

When fixing a bug, add a test that reproduces it first. Changes to `.mrconfig` handling should match how `mr` itself
parses the file.

## Commit message style

This repository follows the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.

Examples:

- `feat: add xyz`
- `fix: correct abc`
- `docs: update wiki structure`

## Pull request expectations

- Keep changes focused and scoped.
- Update docs when behavior changes.
- Ensure CI passes.
- Prefer clear, short descriptions and rationale in the PR body.

## Performance Testing

If you are changing discovery logic, please run the benchmark script before opening a PR to ensure no performance
regression:

```bash
uv run scripts/benchmark.py
```

To compare specific versions or rerun only specific phases:

```bash
# Compare selected refs
uv run scripts/benchmark.py --versions v0.0.1 main --runs 10

# Regenerate summary and plot from existing data.json
uv run scripts/benchmark.py --steps summary,plot --data-file .cache/mr-manager/benchmarks/<id>/data.json
```
