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
markdownlint --config markdownlint.json --ignore-path .markdownlintignore "**/*.md"
```

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
