# Usability & General Analysis — mr-manager

_Analysis date: 2026-06-15. Scope: code structure, UX/TUI flow, CLI ergonomics,
packaging, docs, project process._

## Overall impression

This is a well-above-average side project. The architecture is clean
(`core` / `ui` / `cli`, with a model–controller split for the selection logic),
docstrings are consistent, and the engineering *around* the code is unusually
mature for its size: CI quality gates (ruff, ty, markdownlint, commitlint),
Conventional Commits, a Keep-a-Changelog `CHANGELOG`, semantic-versioned automated
releases, a generated wiki, and even a real benchmarking harness. The core feature
loop (discover → toggle → save) is coherent and the TUI is responsive (compact /
stacked status layout).

The weaknesses are mostly about **reach** (who can install/use it), **scale**
(usability with many repos), and **safety nets** (tests, backups). Below, grouped
and prioritized.

Impact scale: 🔴 High · 🟠 Medium · 🟡 Low · 🔵 Polish.

---

## A. Reach & adoption

### 🔴 A.1 `requires-python = ">=3.13"` is unjustifiably strict

`pyproject.toml:10`, `.python-version`

I checked the source for anything that actually needs 3.13 (PEP 695 type params,
`match`, `tomllib`, etc.) — **there is none**. The code uses
`from __future__ import annotations`, `X | None`, dataclasses, and pathlib, all of
which work on much older versions. Pinning to 3.13 (released late 2024) excludes the
large majority of users still on 3.10–3.12 for **no technical reason**.

The only thing nudging the floor upward is `datetime.UTC` (3.11+) in the benchmark
script — which isn't shipped to end users. **Recommendation:** lower
`requires-python` to `>=3.11` (or `>=3.10` if you replace `datetime.UTC` with
`timezone.utc`). For a tool meant to be `pipx install`ed widely, this single line is
probably your biggest adoption lever.

### 🟠 A.2 `.mrconfig` location is hardcoded — no XDG support

`ui/selection/model.py:17` (`config_path = Path.home() / ".mrconfig"`)

Modern myrepos also reads `$XDG_CONFIG_HOME/mr/config` (i.e. `~/.config/mr/config`).
Users who keep their config there will open mr-manager and see **none** of their
configured repos (and a save would create a competing `~/.mrconfig`). The config
path is also not exposed in the config editor.

**Recommendation:** resolve the config path the way `mr` does (env `MR_CONFIG` if
set, then `~/.mrconfig`, then `$XDG_CONFIG_HOME/mr/config`), and/or make it editable
in the config modal.

---

## B. Usability at scale

### 🟠 B.1 No search / filter

With a home directory full of repos the list can be long; there's no way to filter.
A simple incremental filter input (type to narrow) would be the highest-value UX
addition. Textual makes this cheap.

### 🟠 B.2 No bulk operations

Toggling repos one-by-one with `space` doesn't scale. Add "toggle all visible",
"select none", and ideally "select all under <dir>". Pairs naturally with B.1
(toggle-all-filtered).

### 🟡 B.3 Discovery scope is broad and the ignore list is platform-skewed

`core/discovery.py:8-25`

`_IGNORED_DISCOVERY_DIRS` is hardcoded and macOS/Windows-leaning (`Library`,
`Movies`, `Music`, `Pictures`, `Public`). On Linux it misses common heavy trees
(`.m2`, `.gradle`, `go/pkg`, `.cache` is covered, `snap`, `.local/share`). Scanning
all of `$HOME` is also just slow on large homes (mitigated by the cache, but the
first/`r` scan still pays it).

**Recommendations:** (a) make the ignore list user-configurable; (b) consider a
configurable max depth; (c) document that discovery starts at `discovery_root` so
users can narrow it themselves (this already exists — surface it more in the README).

### 🟡 B.4 Silent skip of unreadable directories

`os.walk(..., onerror=None)` means permission-denied subtrees vanish without a word.
A user wondering "why isn't repo X listed?" gets no signal. Consider counting/most
recent error and showing "N directories skipped (perm?)" in the status line.

---

## C. CLI ergonomics

### 🟠 C.1 No `--help`, no `--version`; argv hand-parsed

`cli/version_flag.py:16-29`, `main.py`

`handle_version_flag` scans `sys.argv` for the literal `-v`. Consequences:

- `mr-manager --help` / `-h` **launches the TUI** instead of printing help — a
  surprise for anyone probing a new CLI.
- `--version` (the conventional long form) does nothing.
- Any unknown flag is silently ignored.

**Recommendation:** use `argparse` (stdlib, zero deps) for `-h/--help`,
`-v/--version`. It also future-proofs adding flags like `--config`, `--root`,
`--no-cache`. (Typer/Click are options but argparse keeps the dependency footprint
at zero, consistent with the project's minimalism.)

---

## D. Safety nets & correctness

### 🔴 D.1 No tests

There is no `tests/` directory at all. The riskiest logic in the app —
parsing `.mrconfig`, removing sections by name, normalizing path spellings, and
rewriting the file — is exactly the logic a user would be most upset to see
regress, because it edits a file they hand-maintain. Even a handful of round-trip
tests (`parse → toggle → write → re-parse`) plus quoting/edge-case tests would pay
for themselves. This is both a quality and a *data-safety* issue.

### 🟠 D.2 No backup / atomic write before overwriting `.mrconfig`

(Also in the security report.) `write_config_updates` overwrites the whole file
with a plain `write_text`. A crash mid-write truncates it, and there's no `.bak`.
For a tool whose entire purpose is editing this file, write atomically
(temp + `os.replace`) and keep one backup.

### 🟡 D.3 Hand-rolled YAML parser is fragile for hand-edited config

`core/user_config.py:45-80`

The parser accepts only a narrow subset (two-space-indented block mapping, no flow
style, no lists, no tabs). A user who hand-edits `config.yaml` with otherwise-valid
YAML (e.g. tabs, `discovery: {root_path: ...}`) gets a `ValueError`. Since this is a
user-facing config file, either (a) use `yaml.safe_load` / `tomllib` (switch the
file to TOML — arguably a better fit and `tomllib` is stdlib), or (b) clearly
document the accepted subset in the README and the file header. Today the format is
undocumented and stricter than it looks.

### 🟡 D.4 Save writes immediately with no diff preview

`save` commits changes after only a counts summary ("To Add / To Remove"). A
"review changes" view (which sections will be added/removed) before writing would
reduce mistakes, especially once bulk operations (B.2) exist.

---

## E. Docs & process (mostly strengths)

- 🔵 README is clear and badge-rich; keybindings and config are documented. Good.
  Add a short note that discovery starts at `discovery_root` and how to narrow it
  (ties to B.3), and document the config-file format (D.3).
- 🔵 `CHANGELOG.md` follows Keep a Changelog and is genuinely maintained. 
- 🔵 Conventional Commits + commitlint + semantic release is a clean pipeline.
- 🔵 The benchmarking harness (`scripts/benchmark.py`) is impressive for a project
  this size — worktree isolation, cold/warm runs, percentile stats, plots. Nice.
- 🔵 `.idea/vcs.xml` is tracked; recommend untracking `.idea/` entirely to avoid
  IDE-specific noise in the repo.

---

## F. Smaller polish items

- 🔵 Bullet glyphs (`●○◐◌`) and the single accent color assume a Unicode-capable
  terminal/font; fine for the target audience, but a brief "requires a modern
  terminal" note avoids confused issues.
- 🔵 `j`/`k` are bound for movement; confirm arrow keys also work (OptionList's
  built-ins) and mention both in the README for discoverability.
- 🔵 The status line truncates long errors. For config-parse failures, a slightly
  more actionable message (which key/line) would help.
- 🔵 Consider an optional "run `mr update` after save" affordance — currently the
  tool stops at editing config, leaving the user to switch tools. Scope decision,
  but it would close the loop.

---

## Prioritized action list

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 1 | Lower `requires-python` to `>=3.11` (drop the 3.13 pin) | 🔴 | Trivial |
| 2 | Add tests for config parse/modify/write round-trip | 🔴 | Med |
| 3 | Support XDG (`~/.config/mr/config`) + `MR_CONFIG` for `.mrconfig` | 🟠 | Low |
| 4 | Add incremental search/filter to the repo list | 🟠 | Med |
| 5 | Add bulk toggle (all / none / filtered) | 🟠 | Low |
| 6 | Atomic write + `.mrconfig.bak` backup | 🟠 | Low |
| 7 | Proper CLI with argparse (`-h/--help`, `--version`) | 🟠 | Low |
| 8 | Make discovery ignore-list configurable; document root narrowing | 🟡 | Low |
| 9 | Switch config to TOML (`tomllib`) or document the YAML subset | 🟡 | Low |
| 10 | Untrack `.idea/`; minor README/error-message polish | 🔵 | Trivial |
