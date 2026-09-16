# Security Analysis — mr-manager

_Analysis date: 2026-06-15. Scope: full source tree, CI/CD workflows, packaging, release pipeline._

## TL;DR

`mr-manager` is a local, single-user TUI with a tiny attack surface (one runtime
dependency, no network calls, no privilege boundary). There is no classic
remote-exploitation surface. The interesting risk lives in two places:

1. **CI/CD supply chain** — the release pipeline has PyPI publishing rights and
   uses mutable action tags + over-broad permissions.
2. **Data integrity** — the tool rewrites the user's `~/.mrconfig` non-atomically
   with no backup, and there are no tests guarding that logic.

Neither of these is a "drop everything" issue for a personal tool, but both are
worth fixing properly.

Severity scale: 🔴 High · 🟠 Medium · 🟡 Low · 🔵 Informational / hardening.

---

## 1. Application code

### 🟠 1.1 Non-atomic config writes — data-loss / corruption risk

`config.py:192-193`, `core/user_config.py:160-161`, `core/cache.py:56-59`

All three writers do `path.write_text(...)` directly. If the process is killed
(or the disk fills) mid-write, the user's `~/.mrconfig` is left **truncated**.
Because mr-manager rewrites the *entire* file (preserved sections + additions),
a crash here destroys hand-maintained config. There is also no backup taken before
the overwrite.

This is the most impactful integrity issue in the codebase: `.mrconfig` is
user-authored data, and the tool's whole job is to rewrite it.

**Recommendation:** write atomically — temp file in the same directory + `os.replace()`
(atomic rename on POSIX). Optionally keep a `~/.mrconfig.bak` of the previous content
before the first write. Apply the same pattern to `config.yaml` and the cache.

### 🟡 1.2 No concurrency guard on config writes

`controller.save_changes()` → `write_config_updates`

Two concurrent mr-manager instances (or mr-manager racing a hand edit) produce
last-write-wins / lost updates. Low risk for a single-user TUI, but combined with
1.1 it argues for write-temp-then-rename plus an advisory lock or a read-verify
before write.

### 🟡 1.3 Cache file is trusted input that flows into `.mrconfig`

`core/cache.py:41-47`

`load_cached_repositories` reads `~/.cache/mr-manager/discovery_cache.json` and the
paths become selectable rows that can be written into `.mrconfig`. The `isinstance(p, str)`
check is good defensive coding, but the contents are otherwise trusted. An attacker
who can write to `~/.cache` could influence which paths appear — however such an
attacker already has the user's privileges, so this is essentially non-exploitable.
Noted for completeness; no action required beyond the existing validation.

### 🔵 1.4 Hand-rolled YAML parser (positive note + caveat)

`core/user_config.py:45-80`

Rolling a minimal parser instead of `yaml.safe_load` *avoids* the classic
`yaml.load` RCE footgun and adds zero dependencies — a reasonable security tradeoff.
The input is the user's own file (trusted), so this is fine security-wise. The
caveat is robustness, not security (see the usability report).

### 🔵 1.5 Filesystem discovery — safe by default

`core/discovery.py:42-61`

`os.walk` runs with `followlinks=False` (default), so symlinked directories are not
descended — this avoids symlink-escape of the scan root and infinite loops. Good.
Permission-denied directories are silently skipped (`onerror=None`), which is safe
(no traversal) though it hides errors (usability note).

### 🔵 1.6 `subprocess` usage is clean

`config.py:126-131`, `scripts/benchmark.py`

All `subprocess.run` calls use argument lists (no `shell=True`), handle
`FileNotFoundError`, and use `check=False` with explicit result handling. No shell
injection from the application code. Good.

---

## 2. CI/CD & supply chain (highest-value section)

### 🟠 2.1 Third-party actions pinned to mutable tags, not commit SHAs

All workflows reference actions by major-version tag (`@v6`, `@v7`, `@v2`, `@v5`).
Tags are mutable: if a third-party action's repo is compromised, an attacker can
move the tag to a malicious commit and it is pulled on the next run. This matters
most where the token is powerful:

- `release.yml`: `mindsers/changelog-reader-action@v2` runs in a job, and the
  release pipeline holds **PyPI publish (OIDC) + `contents: write`**.
- `wiki.yml`: `Andrew-Chen-Wang/github-wiki-action@v5` runs with **`contents: write`**.
- `benchmark.yml`: `thollander/actions-comment-pull-request@v3`.

**Recommendation:** pin third-party actions to full commit SHAs (with a comment
noting the version), e.g.
`mindsers/changelog-reader-action@<sha> # v2.x`. Let Dependabot bump the SHAs (it
already manages `github-actions`). First-party `actions/*` are lower risk but
SHA-pinning them too is the consistent best practice.

### 🟠 2.2 Over-broad permissions in the release job

`.github/workflows/release.yml` — `publish-pypi` job:

```yaml
permissions:
  id-token: write   # correct — OIDC trusted publishing to PyPI, no long-lived token
  actions: write    # not needed
```

`id-token: write` for trusted publishing is exactly right (no PyPI API token stored —
good). But `actions: write` grants the run the ability to cancel/re-run workflows
and delete artifacts; nothing in the job needs it (`upload-artifact@v7` uses the
implicit run token). Drop `actions: write`.

### 🟡 2.3 `benchmark.yml`: `pull-requests: write` is ineffective for fork PRs (and that's the *safe* state)

`benchmark.yml` triggers on `pull_request` and declares `pull-requests: write` to
post a comment. For PRs **from forks**, GitHub downgrades `GITHUB_TOKEN` to
read-only regardless of the `permissions:` block, so the comment step will fail on
fork PRs (it works only for same-repo branch PRs). This is a functional gap, not a
vuln.

**Important:** the tempting "fix" — switching to `pull_request_target` — would be a
**security regression**, because that trigger runs with a writable token *and*
secrets while the job executes untrusted PR code (`uv sync --dev`, `uv run scripts/...`,
`git checkout` of arbitrary refs). Do **not** do that. If fork-PR comments are
wanted, use the split `workflow_run` pattern (untrusted job uploads an artifact; a
separate trusted workflow posts the comment). The current `pull_request` setup is
correctly the safe choice.

### 🔵 2.4 Untrusted code execution in `benchmark.yml` (acceptable as-is)

The benchmark job runs PR-supplied code and installs PR-defined dependencies. Because
it runs under `pull_request` with no secrets and a read-only token, the blast radius
is the ephemeral runner only. Acceptable. Just keep it that way (see 2.3).

### 🔵 2.5 Unpinned transitive tooling installs

`pr_quality_checks.yml` / `code_quality_checks.yml` run `npm install -g @commitlint/cli ...`
and `markdownlint-cli` with no version pin, fetching latest at run time. Low risk
(no secrets in these jobs), but pinning versions improves reproducibility and
shrinks the supply-chain window.

---

## 3. Packaging / secrets / repo hygiene

- 🔵 **No secrets committed.** Only `.idea/vcs.xml` is tracked from `.idea/`
  (benign); `workspace.xml` (which can leak local paths) is correctly untracked.
  `.DS_Store` and `dist/` are gitignored. Recommend untracking `.idea/` entirely.
- 🔵 **Minimal dependency surface** — one runtime dep (`textual`). `uv.lock` is
  committed (reproducible dev builds). Dependabot covers both `github-actions` and
  the `uv` ecosystem, so `textual` updates land as PRs. Good.
- 🟡 **No dependency vulnerability scanning** in CI. Add `uvx pip-audit` (or
  `osv-scanner`) as a quick gate. Low effort, catches advisories in `textual`/transitives.
- 🟡 **No security linting.** Ruff only enables `E, F, I` (`pyproject.toml:37`).
  Adding `S` (flake8-bandit) and `B` (bugbear) gives cheap static security/bug
  coverage with no new dependency.
- 🔵 **Release provenance:** with OIDC publishing you can also emit PEP 740
  attestations / build provenance for the PyPI artifacts. Optional, nice-to-have.

---

## 4. The cross-cutting issue: no tests

There is no `tests/` directory. The most security-relevant code —
`write_config_updates`, `_remove_sections_by_name`, section parsing/normalization,
and the shell-quoting helper — has zero automated coverage, yet it **rewrites the
user's `.mrconfig`**. A regression here silently corrupts user data. Tests for the
config read/modify/write round-trip (including quoting edge cases) are the single
highest-leverage safety improvement.

---

## Prioritized action list

| # | Item | Severity | Effort |
|---|------|----------|--------|
| 1 | Atomic writes (temp + `os.replace`) + `.mrconfig.bak` backup | 🟠 | Low |
| 2 | Add tests around config read/modify/write + quoting | 🟠 (safety) | Med |
| 3 | SHA-pin third-party actions (esp. release & wiki) | 🟠 | Low |
| 4 | Drop `actions: write` from release job | 🟠 | Trivial |
| 5 | Add `pip-audit` + ruff `S`,`B` to CI | 🟡 | Low |
| 6 | Untrack `.idea/`; pin npm tool versions | 🔵 | Trivial |
