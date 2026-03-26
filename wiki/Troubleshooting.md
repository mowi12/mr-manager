# Troubleshooting

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
- Re-run and inspect status text in the top-right area of the UI.

## Type or lint errors locally

Run the full local checks:

```bash
uv run ruff check --no-fix .
uv run ruff format --check .
uv run ty check
markdownlint --config markdownlint.json --ignore-path .markdownlintignore "**/*.md"
```
