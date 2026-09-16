# AGENTS

## Overview

This repository contains **mr-manager**: a [Textual](https://textual.textualize.io/) TUI for managing
repository sections in the user's `~/.mrconfig` [myrepos](https://myrepos.branchable.com/) file. It scans the
home directory for local Git repositories, reads the repos already configured in `~/.mrconfig`, and lets the
user toggle which ones are tracked — then writes the add/remove changes back. It is a single, self-contained
Python package published to PyPI (`pipx install mr-manager`). Prefer referencing the README and wiki over
restating them here; if you must summarize, keep it short and point to the canonical page.

### Project links

- Repository: https://github.com/mowi12/mr-manager
- Wiki: https://github.com/mowi12/mr-manager/wiki
- DeepWiki: https://deepwiki.com/mowi12/mr-manager
- PyPI: https://pypi.org/project/mr-manager/
- Upstream tool this manages: https://myrepos.branchable.com/ (myrepos / `mr`)

### Canonical documentation and what each covers

- README.md — install (pipx / from source), usage, keybindings, user-config keys, dev workflow, benchmarking
- wiki/Home.md — wiki entry page and feature summary
- wiki/Contribution-Guidelines.md — prerequisites, setup, quality checks, commit style, PR expectations
- wiki/Release-Process.md — how a release is cut (tag → PyPI + GitHub release)
- wiki/Troubleshooting.md — common runtime issues
- CHANGELOG.md — Keep a Changelog; SemVer; one entry per release (drives GitHub release notes)

## Structure

```
.
├── src/mr_manager/
│   ├── main.py                 # entry point: `-v` preflight flag, then launch the TUI
│   ├── cli/
│   │   └── version_flag.py     # handle_version_flag / get_installed_version (importlib.metadata)
│   ├── core/                   # framework-free logic — must NOT import Textual
│   │   ├── config.py           # ~/.mrconfig parse + add/remove section rewrite (shell quoting, git clone source)
│   │   ├── discovery.py        # recursive os.walk scan for `.git` dirs (ignore list, no symlink follow)
│   │   ├── cache.py            # discovery cache at ~/.cache/mr-manager/discovery_cache.json (TTL-gated)
│   │   └── user_config.py      # ~/.config/mr-manager/config.yaml (minimal hand-rolled YAML parser/writer)
│   └── ui/                     # Textual layer
│       ├── app.py              # MrManagerApp: key bindings, threaded workers, scan-status layout
│       ├── action_modal.py     # reusable confirm/cancel modal (ActionModal)
│       ├── config_editor_modal.py # edit discovery root + cache TTL (ConfigEditorModal)
│       ├── ui.tcss             # Textual CSS
│       └── selection/
│           ├── controller.py   # RepositorySelectionController: orchestrates core ops over the model
│           └── model.py        # RepositorySelectionModel: UI state dataclass
├── scripts/
│   ├── benchmark.py            # startup benchmark across git refs (run via `uv run`; PEP 723 inline deps)
│   └── add_auto_gen_wiki_hint.sh # prepends "auto-generated" notice to wiki/*.md in CI
├── wiki/                       # canonical docs; published to GitHub Wiki by wiki.yml
├── assets/screenshots/         # README images
├── .github/
│   ├── workflows/              # release, code_quality_checks, pr_quality_checks, benchmark, wiki, setup/
│   ├── ISSUE_TEMPLATE/         # bug, feature, refactor, docs, question templates + config
│   ├── dependabot.yml          # github-actions + uv ecosystems, monthly
│   ├── semantic.yml            # semantic-pull-requests app config (check commits)
│   └── pull_request_template.md
├── pyproject.toml              # hatchling + hatch-vcs build; deps; ruff + ty config
├── uv.lock                     # pinned dev/runtime resolution
├── CHANGELOG.md                # Keep a Changelog
├── README.md
├── markdownlint.json, .markdownlintignore, commitlint.config.js, .python-version
└── LICENSE
```

## Where to look

| Task                                   | Location                                  | Notes                                                                 |
| -------------------------------------- | ----------------------------------------- | --------------------------------------------------------------------- |
| Project overview / get started         | README.md                                 | Install, usage, keybindings, config keys, dev workflow.               |
| Entry point / CLI flags                | src/mr_manager/main.py, cli/version_flag.py | `-v` is handled pre-launch; everything else starts the TUI.         |
| `.mrconfig` parsing & rewrite          | src/mr_manager/core/config.py             | Section parsing, add/remove, shell-quoting, `git clone` source resolution. |
| Repository discovery (filesystem scan) | src/mr_manager/core/discovery.py          | `os.walk` from discovery root; `_IGNORED_DISCOVERY_DIRS`; stops at `.git`. |
| Discovery cache                        | src/mr_manager/core/cache.py              | JSON cache + TTL in hours; fails open on corrupt/unreadable.          |
| User settings (root, cache TTL)        | src/mr_manager/core/user_config.py        | `~/.config/mr-manager/config.yaml`; minimal YAML subset.             |
| TUI app / key bindings / workers       | src/mr_manager/ui/app.py                  | Threaded scan + save workers; responsive scan-status row.            |
| Selection state ↔ core orchestration   | src/mr_manager/ui/selection/{controller,model}.py | Business logic lives here, not in `app.py`.                  |
| Modals (confirm, config editor)        | src/mr_manager/ui/{action_modal,config_editor_modal}.py | Reusable; return results to `app.py` callbacks.       |
| Styling                                | src/mr_manager/ui/ui.tcss                 | Textual CSS.                                                          |
| Performance benchmarking               | scripts/benchmark.py                      | Cold/warm runs over git refs; artifacts in `.cache/mr-manager/benchmarks/`. |
| Release procedure                      | wiki/Release-Process.md, .github/workflows/release.yml | Tag `v*` → PyPI (OIDC) + GitHub release from CHANGELOG. |
| CI quality gates                       | .github/workflows/{code_quality_checks,pr_quality_checks}.yml | ruff, ty, markdownlint, commitlint.            |

## Architecture and patterns

- **Layering:** `cli` (preflight flags) → `ui` (Textual) → `core` (pure logic). **`core/` is framework-free
  and must not import Textual**; the UI depends on core, never the reverse. Keep business logic in
  `ui/selection/controller.py` and `core/`, not in `app.py`.
- **Model–controller split:** `RepositorySelectionModel` (a `@dataclass`) holds UI state;
  `RepositorySelectionController` mutates it and calls into `core`. `MrManagerApp` is a thin view that renders
  the model and forwards user actions to the controller.
- **Threaded workers:** long-running work (filesystem scan, config save) runs in Textual
  `@work(thread=True, exclusive=True)` workers; results are marshalled back with `call_from_thread` so the UI
  thread never blocks.
- **Discovery:** `os.walk(topdown=True)` from the configured root, pruning `_IGNORED_DISCOVERY_DIRS` and not
  descending into a repo's working tree once `.git` is found. `followlinks` is left at the default `False`
  (no symlink escape).
- **Caching:** discovered paths are cached as JSON at `~/.cache/mr-manager/discovery_cache.json` with a
  TTL (hours, default 24). Cache reads fail open (corrupt/unreadable → treated as a miss). `r` forces a rescan.
- **`.mrconfig` writes:** the whole file is rewritten — unknown sections are preserved, named sections are
  removed by their original header text, and new `[path]` + `checkout = git clone …` blocks are appended.
  Values written into the file are shell-quoted (`_shell_single_quote`); the clone source comes from
  `git config --get remote.origin.url` via a **list-arg** `subprocess.run` (never `shell=True`).
- **Versioning:** version is derived from git tags by `hatch-vcs` at build time (`[tool.hatch.version]`,
  `dynamic = ["version"]`) and read at runtime via `importlib.metadata`.

## Boundaries

- Always do: keep the `cli`/`core`/`ui` layering and the model–controller split; put new logic in
  `controller.py` or `core/`, not in `app.py`; preserve unknown sections when rewriting `~/.mrconfig`;
  shell-quote any value written into `~/.mrconfig`; use list-arg `subprocess` (no `shell=True`); keep `core/`
  free of Textual imports; update README/wiki and CHANGELOG when behavior changes.
- Ask first: changing the `~/.mrconfig` format/path, the user-config format/path/keys (stabilized in v1.0.1 —
  see CHANGELOG), or the cache location/format; bumping `requires-python`; adding a runtime dependency (only
  `textual` today); editing CI — especially `release.yml` (PyPI trusted publishing) and its `permissions`.
- Never do: commit secrets or tokens; push to `main` directly (PRs only); introduce `shell=True` or weaken
  the `.mrconfig` shell-quoting; commit `dist/`, `.cache/` benchmark artifacts, or `.DS_Store`; reference
  third-party GitHub Actions from an untrusted fork.

## Commands (run from repo root)

### Setup and run

- Install deps (incl. dev): `uv sync --dev`
- Run the TUI: `uv run mr-manager`
- Print version and exit: `uv run mr-manager -v`

### Lint / format / type-check

- Lint: `uv run ruff check --no-fix .`
- Format check: `uv run ruff format --check .`
- Type check: `uv run ty check`
- Markdown lint: `markdownlint --config markdownlint.json --ignore-path .markdownlintignore "**/*.md"`

### Benchmark

- Quick run: `uv run scripts/benchmark.py --runs 5`
- CI-style (text only): `uv run scripts/benchmark.py --runs 10 --steps collect,summary`
- Specific refs / scan root: `uv run scripts/benchmark.py --versions v0.0.1 main --scan-root <path>`

### Build / publish

- Build sdist + wheel: `uv build`
- Publish (normally CI-only via OIDC): `uv publish`

## Style, checks, and tests

- **Style:** Ruff with rules `E, F, I`, `line-length = 100`, `target-version = "py313"`, auto-fix on
  (`pyproject.toml`). Type-checked with `ty`. Markdown follows `markdownlint.json`.
- **Docstrings:** modules/functions use short Google-style docstrings with `Args:` / `Returns:` / `Raises:`
  where relevant; comment only non-obvious logic. Match the surrounding style.
- **Tests:** there is currently **no automated test suite** in this repo. When adding tests, prefer pytest and
  exercise `core/` and `controller.py` directly (they're framework-free / framework-light); reserve full-app
  tests for a couple of Textual `App.run_test()` smoke checks.

## Issues

- Use `.github/ISSUE_TEMPLATE/` to pick the right template (bug report, feature request, refactor,
  documentation, question/support).

## PRs

- Use `.github/pull_request_template.md` for the required sections. Keep changes focused; ensure CI passes;
  update docs/CHANGELOG when behavior changes.

## Git and CI conventions

- **Branching:** `main` only. PRs target `main`; there is no `develop` branch. Push to `main` is via merged PRs.
- **CI on PRs:** `code_quality_checks.yml` (ruff lint + format, `ty`, markdownlint),
  `pr_quality_checks.yml` (commitlint over PR commits), and `benchmark.yml` (runs the startup benchmark on PRs
  and comments results — note the comment step can't post on fork PRs by design) all run on `pull_request`
  only. Each uses a `concurrency` group (`cancel-in-progress`), per-job `timeout-minutes`, and
  `persist-credentials: false` on checkout. Since checks no longer run on `push: main`, `main` stays validated
  via branch protection's "Require branches to be up to date before merging".
- **Releases:** push a `v*` tag → `release.yml` builds, publishes to PyPI via **OIDC trusted publishing**
  (`id-token: write`, `environment: pypi` — no stored token), then creates a GitHub release whose notes come
  from the matching CHANGELOG section.
- **Wiki:** `wiki/**` changes on `main` are published to the GitHub Wiki by `wiki.yml`
  (`add_auto_gen_wiki_hint.sh` stamps an auto-generated notice).
- **Dependencies:** Dependabot updates the `github-actions` and `uv` ecosystems monthly
  (`.github/dependabot.yml`); dev tooling is grouped.

## Conventional commits

Commit messages and PR commits follow [Conventional Commits](https://www.conventionalcommits.org/) with a short
lowercase type prefix and optional scope. Common types: `feat`, `fix`, `refactor`, `docs`, `chore`, `ci`,
`test`. Keep the subject imperative and concise. Enforced in CI by commitlint (`commitlint.config.js`) and on
PRs by the semantic-pull-requests app (`.github/semantic.yml`).
