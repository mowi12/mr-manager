# Security Remediation Guide — mr-manager

Companion to `SECURITY_ANALYSIS.md`. Each section takes one finding and explains
**exactly how to fix it**, with drop-in code/config that matches the project's
existing style. Ordered roughly by value (the prioritized table from the analysis).

Conventions used below:
- File paths are relative to the repo root.
- "Verify" lines tell you how to confirm the fix.
- Where a framework/3rd-party API detail could drift, it's flagged so you check it.

---

## 1. Atomic config writes + backup (🟠 1.1 / D.2)

**Problem.** `write_config_updates` (`src/mr_manager/core/config.py:192-193`),
`save_user_config` (`core/user_config.py:160-161`), and `save_cached_repositories`
(`core/cache.py:56-59`) all call `path.write_text(...)` directly. A crash, full
disk, or `kill` mid-write leaves a **truncated** file. For `~/.mrconfig` that means
destroyed user data, and there's no backup.

**Fix.** Write to a temp file in the *same directory*, `fsync`, then `os.replace()`
(atomic rename on the same filesystem). Optionally snapshot a `.bak` first.

Add a small shared helper. Create `src/mr_manager/core/atomic_io.py`:

```python
"""Atomic file-write helpers to avoid partial writes on crash."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, keep_backup: bool = False) -> None:
    """Write text to `path` atomically via a temp file and rename.

    Args:
        path: Destination file path.
        content: Full file contents to write.
        keep_backup: When True, copy the previous file to `<path>.bak` first.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if keep_backup and path.exists():
        backup_path = path.with_name(path.name + ".bak")
        backup_path.write_bytes(path.read_bytes())

    # Temp file must live on the same filesystem as `path` for os.replace to be atomic.
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
```

Then route the three writers through it.

In `core/config.py`, replace the tail of `write_config_updates`:

```python
    # was: config_path.parent.mkdir(...); config_path.write_text(updated_text, ...)
    atomic_write_text(config_path, updated_text, keep_backup=True)
```

In `core/user_config.py`, in `save_user_config`:

```python
    atomic_write_text(resolved_config_path, config_text)
```

In `core/cache.py`, in `save_cached_repositories` (keep the graceful `except OSError`):

```python
    try:
        atomic_write_text(_CACHE_FILE, json.dumps(data))
    except OSError:
        pass
```

Add the import (`from mr_manager.core.atomic_io import atomic_write_text`) to each.

**Caveat.** `os.replace` is atomic only within one filesystem. Since the temp file
is created in the destination's own directory, this holds even when `~` is a
mounted/overlay FS. The `.bak` only protects against the *previous* good state, not
concurrent edits (see analysis §1.2).

**Verify.** Add a test that writes a config, then simulate failure by patching
`os.replace` to raise and assert the original file is intact and no `.tmp` remains.

---

## 2. Tests for the config read/modify/write logic (🟠 §4 / D.1)

**Problem.** The code that rewrites `~/.mrconfig` has zero tests. Regressions here
silently corrupt user data.

**Fix.** Add `pytest` and a `tests/` package. This is also the harness you'll use to
verify several other fixes in this guide.

`pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "ruff>=0.15.7",
    "ty>=0.0.24",
    "pytest>=8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`tests/test_config_roundtrip.py` (covers the highest-risk paths — parse, remove,
quote, round-trip):

```python
from pathlib import Path

from mr_manager.core.config import (
    parse_configured_repo_sections,
    write_config_updates,
)


def test_roundtrip_add_then_parse(tmp_path: Path) -> None:
    config = tmp_path / ".mrconfig"
    repo = tmp_path / "projects" / "demo"
    repo.mkdir(parents=True)

    write_config_updates(config, repos_to_add=[repo], section_names_to_remove=set())

    parsed = parse_configured_repo_sections(config)
    assert repo.resolve() in parsed


def test_remove_preserves_other_sections(tmp_path: Path) -> None:
    config = tmp_path / ".mrconfig"
    config.write_text(
        "[DEFAULT]\n# keep me\n\n[projects/a]\ncheckout = git clone 'x' 'a'\n"
        "\n[projects/b]\ncheckout = git clone 'y' 'b'\n",
        encoding="utf-8",
    )
    write_config_updates(config, repos_to_add=[], section_names_to_remove={"projects/a"})

    text = config.read_text(encoding="utf-8")
    assert "[projects/a]" not in text
    assert "[projects/b]" in text
    assert "# keep me" in text  # DEFAULT body preserved


def test_clone_target_with_quote_is_escaped(tmp_path: Path) -> None:
    config = tmp_path / ".mrconfig"
    repo = tmp_path / "weird'name"
    repo.mkdir()
    write_config_updates(config, repos_to_add=[repo], section_names_to_remove=set())
    # Single quote must be escaped as '"'"', never left bare inside the quoted arg.
    assert "'\"'\"'" in config.read_text(encoding="utf-8")
```

Add a CI job in `.github/workflows/code_quality_checks.yml`:

```yaml
  test-python:
    name: Test Python
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Set Up Python Tooling
        uses: ./.github/workflows/setup
      - name: Run pytest
        run: uv run pytest
```

**Verify.** `uv run pytest` passes locally and in CI.

---

## 3. SHA-pin third-party actions (🟠 2.1)

**Problem.** Workflows reference actions by mutable major tags. A compromised
third-party action repo can move `@v5` to a malicious commit, pulled on the next run
— and your release/wiki jobs run with publish + `contents: write` rights.

**Fix.** Pin to full commit SHAs, keeping the human-readable version in a comment.
Get the SHA the tag currently points to:

```bash
gh api repos/mindsers/changelog-reader-action/git/refs/tags/v2 \
  --jq '.object.sha'
# For annotated tags, dereference:
gh api repos/<owner>/<repo>/commits/<tag> --jq '.sha'
```

Then rewrite the references. Highest priority (powerful tokens):

```yaml
# release.yml
- uses: mindsers/changelog-reader-action@<sha>   # v2.x

# wiki.yml  (runs with contents: write)
- uses: Andrew-Chen-Wang/github-wiki-action@<sha>  # v5.x

# benchmark.yml
- uses: thollander/actions-comment-pull-request@<sha>  # v3.x
```

First-party `actions/*` (`checkout`, `setup-python`, `upload-artifact`, …) are lower
risk, but pinning them too is the consistent best practice and costs nothing.

**Keep them updated.** Dependabot already manages the `github-actions` ecosystem
(`.github/dependabot.yml`); it bumps SHA pins and updates the version comment, so you
don't lose update automation.

**Verify.** `grep -rnE '@v[0-9]' .github/` returns only intentional first-party
references (or nothing, if you pin those too).

---

## 4. Drop `actions: write` from the release job (🟠 2.2)

**Problem.** `release.yml` → `publish-pypi` grants `actions: write`, which allows
cancelling/re-running workflows and deleting artifacts. Nothing in the job needs it
(`upload-artifact@v7` uses the implicit run token).

**Fix.** Remove the line; keep `id-token: write` (required for OIDC trusted
publishing to PyPI — this is the right, token-less approach):

```yaml
  publish-pypi:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write   # OIDC trusted publishing to PyPI
      # actions: write  <-- delete this line
```

**Verify.** Re-run a release (or `act`/dry-run): build, upload-artifact, and
`uv publish` all still succeed with only `id-token: write`.

---

## 5. Add dependency + security scanning to CI (🟡 §3)

**Problem.** No vulnerability scanning, and Ruff only enables `E, F, I`
(`pyproject.toml:37`) — no static security/bug lint.

**Fix — Ruff rules** (`pyproject.toml`):

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "S"]   # + bugbear, + flake8-bandit

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]   # asserts are fine in tests
```

Note: `S603`/`S607` (subprocess) may flag the `git` calls. They're safe here
(list args, no shell) — either `# noqa: S603` with a comment at those call sites or
add them to `ignore` after reviewing each.

**Fix — vulnerability scan** — add a CI job (no new project dependency; `uvx` runs
it ephemerally):

```yaml
  audit-python:
    name: Audit Dependencies
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Set Up Python Tooling
        uses: ./.github/workflows/setup
      - name: pip-audit
        run: uvx pip-audit
```

**Verify.** `uv run ruff check .` and `uvx pip-audit` pass locally.

---

## 6. Pin npm tooling versions (🟡 2.5)

**Problem.** `pr_quality_checks.yml` and `code_quality_checks.yml` install
`@commitlint/cli`, `@commitlint/config-conventional`, and `markdownlint-cli` with no
version pin, fetching latest each run.

**Fix.** Pin explicit versions:

```yaml
- name: Install commitlint
  run: npm install -D -g @commitlint/cli@19 @commitlint/config-conventional@19

- name: Install Markdownlint CLI
  run: npm install --global markdownlint-cli@0.43
```

(Use whatever current majors you've validated; bump deliberately.)

**Verify.** Both lint jobs still pass with the pinned versions.

---

## 7. Repo hygiene (🔵 §3)

**Untrack `.idea/`.** Only `.idea/vcs.xml` is tracked today (benign), but IDE files
don't belong in VCS:

```bash
git rm -r --cached .idea
printf '\n.idea/\n' >> .gitignore
```

**Optional — release provenance.** With OIDC publishing you can also emit PEP 740
attestations for the PyPI artifacts (supported by `uv publish` / `gh attestation`),
giving consumers verifiable build provenance. Nice-to-have, not required.

---

## 8. Things that are already correct (leave as-is)

Documented here so a future reviewer doesn't "fix" them into regressions:

- **`benchmark.yml` uses `pull_request`, not `pull_request_target`.** This is the
  safe choice — fork PRs run without secrets and with a read-only token. The
  side effect is that the benchmark comment can't post on fork PRs (the
  `pull-requests: write` permission is downgraded for forks). **Do not** switch to
  `pull_request_target` to "fix" the comment; that runs untrusted PR code with a
  writable token + secrets. If you want fork-PR comments, use the split
  `workflow_run` pattern: the untrusted job uploads the summary as an artifact, and
  a separate trusted workflow (triggered by `workflow_run`) downloads it and posts
  the comment.
- **OIDC trusted publishing** (`id-token: write`, `environment: pypi`) — no PyPI
  token stored. Keep it.
- **`subprocess` calls** use list args, no `shell=True`. Keep that pattern for any
  new external commands.
- **`os.walk(followlinks=False)`** (the default) prevents symlink escape of the scan
  root. Don't enable `followlinks`.

---

## Suggested order of work

1. §1 atomic writes  →  2. §2 tests (lock in §1 and the rest)  →  3. §3 SHA-pin
   actions  →  4. §4 drop `actions: write`  →  5. §5 scanning  →  6. §6–§7
   pinning/hygiene.

§1 and §2 are application code (cover with tests). §3–§7 are CI/config and can be
verified by a single PR run.
