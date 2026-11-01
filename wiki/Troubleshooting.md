# Troubleshooting

## Newly cloned repositories are missing

- `mr-manager` caches discovered repositories for 24 hours to launch instantly.
- If you just cloned a new repository, press `r` in the app to force a fresh scan.

## No repositories discovered

- Verify repositories exist under your home directory.
- Ensure each repository has a `.git` directory.
- Confirm terminal permissions allow directory traversal.

## Save reports no changes

- You only get changes when selection differs from config state.
- Toggle a repository with `space`, then press `s`.

## Config parse or write issues

- Ensure `~/.mrconfig` is readable/writable.
- Check for malformed section headers in the config.
- Section headers must start in the first column, as in `mr`. Indented lines are continuations of the previous value,
  so an indented `[name]` is not a repository section.
- Only the exact `[DEFAULT]` section is reserved. `[default]` is an ordinary repository section.
- Re-run and inspect status text in the top-right area of the UI.

## Test, type or lint errors locally

Run the full local checks:

```bash
uv run ruff check --no-fix .
uv run ruff format --check .
uv run ty check
uv run pytest
markdownlint --config markdownlint.json --ignore-path .markdownlintignore "**/*.md"
```
