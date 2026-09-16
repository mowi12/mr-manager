# Usability Improvement Guide — mr-manager

Companion to `USABILITY_ANALYSIS.md`. Each section takes one finding and explains
**how to implement the improvement** in detail, with code/config that fits the
project's structure (`core` / `ui` / `cli`, model–controller split).

Ordered by the prioritized table in the analysis. Textual API calls are written
against the version in `pyproject.toml` (`textual>=8.1.1`); where an API may have
shifted, it's flagged "verify against your Textual version."

---

## 1. Lower `requires-python` (🔴 A.1)

**Why.** Nothing in the source needs 3.13 — no PEP 695 type params, no `match`, no
`tomllib`. The 3.13 pin (`pyproject.toml:10`, `.python-version`) excludes most users
for no technical reason and is your biggest adoption blocker.

**How.**

1. Decide the floor. The only thing nudging it up is `datetime.UTC` (3.11+) in
   `scripts/benchmark.py` — and that's dev-only, not shipped. So:
   - **`>=3.11`** with no code changes, or
   - **`>=3.10`** if you replace `datetime.UTC` with `timezone.utc` in the
     benchmark script (one line) and confirm no other 3.11+ API is used.

2. Edit `pyproject.toml`:

   ```toml
   requires-python = ">=3.11"
   ```

   ```toml
   [tool.ruff]
   target-version = "py311"
   ```

3. Set `.python-version` to your *dev* interpreter (e.g. `3.13` is fine for local
   dev) — it controls the toolchain, not the published floor. Keep it as the highest
   you test on.

4. **Test the floor in CI** so it can't silently regress. Matrix the quality job:

   ```yaml
   strategy:
     matrix:
       python-version: ["3.11", "3.13"]
   steps:
     - uses: actions/setup-python@v6
       with:
         python-version: ${{ matrix.python-version }}
   ```

   (Replace the composite `setup` action's `python-version-file` with the matrix
   input for this job, or add a dedicated min-version job.)

**Caveat.** Type-check (`ty`) and lint against the *lowest* supported version, not
just 3.13, or you'll let newer syntax slip in.

---

## 2. Tests (🔴 D.1)

See **§2 of `SECURITY_REMEDIATION_GUIDE.md`** for the full pytest setup — it's the
same harness. Beyond the config round-trip tests there, add UX-logic tests that
don't need a running TUI, by testing the **controller** directly:

`tests/test_controller.py`:

```python
from pathlib import Path

from mr_manager.ui.selection.controller import RepositorySelectionController


def test_toggle_then_unsaved_changes(tmp_path: Path) -> None:
    controller = RepositorySelectionController()
    repo = tmp_path / "repo"
    controller.apply_repository_data([repo], {})  # discovered, none configured

    assert controller.has_unsaved_changes() is False
    controller.toggle_repo_by_index(0)            # select it
    assert controller.has_unsaved_changes() is True
    assert repo in controller.repos_to_add()
```

The model–controller split is what makes this easy — lean on it. Most behavior can
be tested without Textual; reserve full-app tests (Textual's `App.run_test()`) for a
couple of smoke tests.

---

## 3. Support the XDG / `mr` config locations (🟠 A.2)

**Why.** `config_path` is hardcoded to `~/.mrconfig`
(`ui/selection/model.py:17`). Modern myrepos also reads
`$XDG_CONFIG_HOME/mr/config`; those users currently see none of their repos.

**How.** Add a resolver in `core/config.py` (it owns config concerns):

```python
import os


def resolve_mr_config_path() -> Path:
    """Resolve the myrepos config path the way `mr` itself does.

    Order: $MR_CONFIG, then ~/.mrconfig, then $XDG_CONFIG_HOME/mr/config
    (defaulting XDG to ~/.config). Falls back to ~/.mrconfig when none exist so
    a first save lands in the conventional location.
    """
    env_override = os.environ.get("MR_CONFIG", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve(strict=False)

    home_config = Path.home() / ".mrconfig"
    if home_config.exists():
        return home_config

    xdg_base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    xdg_root = Path(xdg_base).expanduser() if xdg_base else Path.home() / ".config"
    xdg_config = xdg_root / "mr" / "config"
    if xdg_config.exists():
        return xdg_config

    return home_config
```

Then wire it into the model:

```python
# model.py
from mr_manager.core.config import resolve_mr_config_path

config_path: Path = field(default_factory=resolve_mr_config_path)
```

**Optional UX:** also expose the resolved path read-only in the config editor (and
the active path in the scan-status row), so users can see *which* file is being
edited. If you make it editable, persist it as a new key in `config.yaml`
(`myrepos.config_path`) alongside the existing discovery settings.

**Verify.** Set `MR_CONFIG=/tmp/x` and confirm the TUI reads/writes that file;
unset it with a populated `~/.config/mr/config` and confirm it's picked up.

---

## 4. Incremental search / filter (🟠 B.1)

**Why.** Long repo lists are unnavigable without filtering. Highest-value UX add.

**How (design).** Add a single-line `Input` above the `OptionList`. On each change,
filter `displayed_repos` by substring (case-insensitive) and re-render. Keep the
*selection state* (`selected_repo_paths`) authoritative in the model so filtering
never loses a user's toggles — only the *visible* rows change.

1. **Model:** add a filter field and a derived view.

   ```python
   # model.py
   filter_query: str = ""

   def visible_repos(self) -> list[Path]:
       if not self.filter_query:
           return self.displayed_repos
       needle = self.filter_query.casefold()
       return [r for r in self.displayed_repos if needle in str(r).casefold()]
   ```

2. **Render** from `visible_repos()` instead of `displayed_repos` in
   `_render_repository_list` and index lookups. **Important:** toggling currently
   maps a list index → repo. With filtering, the index is into the *visible* list,
   so `_toggle_repo_by_index` / `toggle_repo_by_index` must index `visible_repos()`,
   not `displayed_repos`. Update the controller accordingly:

   ```python
   # controller.py
   def toggle_repo_by_index(self, index: int) -> Path | None:
       visible = self.model.visible_repos()
       if index < 0 or index >= len(visible):
           return None
       repo = visible[index]
       ...
   ```

3. **UI:** add the input in `compose` and react to changes.

   ```python
   # app.py compose(), inside the content Vertical:
   yield Input(placeholder="Filter… (substring)", id="repo-filter")

   def on_input_changed(self, event: Input.Changed) -> None:
       if event.input.id != "repo-filter":
           return
       self._model.filter_query = event.value
       self._render_repository_list()
       self._update_scan_state_result()
   ```

4. **Focus ergonomics:** add a binding (e.g. `/`) to jump to the filter, and `esc`
   inside the filter clears it and returns focus to the list. Make sure `j/k/space`
   still go to the list, not the input, when the list is focused (they will, since
   bindings are widget-scoped — but verify the filter input doesn't swallow them
   while focused; that's expected while typing).

**Verify against your Textual version:** `Input.Changed`, `OptionList.highlighted`,
and `replace_option_prompt_at_index` signatures.

---

## 5. Bulk toggle: all / none / filtered (🟠 B.2)

**Why.** One-by-one toggling doesn't scale; pairs naturally with filtering.

**How.** Add controller methods that operate on the current *visible* set, then bind
keys.

```python
# controller.py
def select_visible(self, repos: list[Path]) -> None:
    self.model.selected_repo_paths.update(repos)

def deselect_visible(self, repos: list[Path]) -> None:
    self.model.selected_repo_paths.difference_update(repos)

def invert_visible(self, repos: list[Path]) -> None:
    for repo in repos:
        if repo in self.model.selected_repo_paths:
            self.model.selected_repo_paths.discard(repo)
        else:
            self.model.selected_repo_paths.add(repo)
```

```python
# app.py BINDINGS
("a", "select_all", "Select all"),
("n", "select_none", "Select none"),
("i", "invert", "Invert"),

def action_select_all(self) -> None:
    if self._model.loading:
        return
    self._controller.select_visible(self._model.visible_repos())
    self._render_repository_list()
    self._update_scan_state_result()
```

(Define `action_select_none`/`action_invert` the same way.) Because these act on
`visible_repos()`, "select all" after a filter means "select everything matching the
filter" — which is exactly the powerful combo you want.

**Caveat.** Watch out for `a`/`n`/`i` colliding with the filter input while it's
focused — these should only fire when the list (not the filter) has focus. Test both
focus states.

---

## 6. Configurable discovery ignore-list + document root narrowing (🟡 B.3)

**Why.** `_IGNORED_DISCOVERY_DIRS` (`core/discovery.py:8-25`) is hardcoded and
macOS-leaning; Linux users hit heavy trees it doesn't skip (`.m2`, `.gradle`,
`go/pkg`, `snap`, …). Scanning all of `$HOME` is also just slow on the first/`r` scan.

**How.**

1. **Make the ignore list extensible** without losing the sensible defaults. Pass an
   extra set into `discover_git_repositories`:

   ```python
   def discover_git_repositories(
       root: Path, extra_ignored_dirs: frozenset[str] = frozenset()
   ) -> list[Path]:
       ignored = _IGNORED_DISCOVERY_DIRS | extra_ignored_dirs
       ...
       dirs[:] = [d for d in dirs if d not in {".", ".."} and d not in ignored]
   ```

2. **Persist it** as a new config key. Extend `UserConfig`
   (`core/user_config.py`) with `extra_ignored_dirs: frozenset[str] = frozenset()`,
   parse it from `config.yaml` (a comma-separated string keeps your minimal parser
   simple: `discovery.extra_ignored_dirs: .m2, go, .gradle`), and thread it through
   the controller's `load_repository_data` into the discovery call.

3. **(Optional) max depth.** Add `discovery.max_depth`; compute depth as
   `len(Path(current_root).relative_to(root).parts)` in the walk and `dirs.clear()`
   past the limit. Useful for users who only nest repos a few levels deep.

4. **Document root narrowing.** This already exists (`discovery_root` in the config
   editor) but isn't emphasized. Add a README line: "Discovery scans recursively
   from *Discovery Root* (default `~`). Point it at e.g. `~/code` for a much faster,
   focused scan."

**Verify.** A config with `extra_ignored_dirs: go` skips a `~/go` tree; benchmark
(`scripts/benchmark.py`) shows the cold-scan improvement.

---

## 7. Surface skipped/unreadable directories (🟡 B.4)

**Why.** `os.walk` defaults to `onerror=None`, so permission-denied subtrees vanish
silently; users can't tell why a repo is missing.

**How.** Pass an `onerror` callback that counts failures, and report the count.

```python
# discovery.py
def discover_git_repositories(root: Path) -> tuple[list[Path], int]:
    skipped = 0

    def _on_error(_: OSError) -> None:
        nonlocal skipped
        skipped += 1

    discovered: list[Path] = []
    for current_root, dirs, _ in os.walk(root, topdown=True, onerror=_on_error):
        ...
    return sorted(discovered, key=lambda r: str(r).lower()), skipped
```

Thread `skipped` back through the controller/app and append to the scan-status text
when non-zero: `… | Skipped: 3 (unreadable)`. Keep the cache storing only the path
list (don't cache the skip count, or recompute it on `r`).

**Caveat.** This changes the function's return type — update the cache save/load and
the benchmark runner (`RUNNER_CODE` in `scripts/benchmark.py`) which unpacks the
result. Cheap, but don't forget the benchmark path.

---

## 8. Proper CLI: `--help` and `--version` (🟠 C.1)

**Why.** `handle_version_flag` (`cli/version_flag.py`) hand-scans argv for `-v`.
`mr-manager --help`/`-h` *launches the TUI*; `--version` (long form) does nothing;
unknown flags are silently ignored.

**How.** Replace the bespoke scan with stdlib `argparse` (zero new deps, consistent
with the project's minimalism). Rewrite `main.py`:

```python
"""Application entrypoint for mr-manager."""

import argparse

from mr_manager.cli.version_flag import get_installed_version
from mr_manager.ui import MrManagerApp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mr-manager",
        description="TUI for managing repositories in your ~/.mrconfig (myrepos) file.",
    )
    # Keep -v working; add the conventional --version long form.
    try:
        installed_version = get_installed_version()
    except RuntimeError:
        installed_version = "unknown"
    parser.add_argument(
        "-v", "--version", action="version", version=f"mr-manager {installed_version}"
    )
    return parser


def main() -> None:
    """Parse preflight flags, then start the Textual application."""
    _build_parser().parse_args()  # handles -h/--help and -v/--version (and exits)
    MrManagerApp().run()


if __name__ == "__main__":
    main()
```

This preserves the existing `-v` contract (the README documents `mr-manager -v`),
adds `--version` and real `--help`, and rejects unknown flags with a usage message.
It also gives you a clean place to add future flags (`--config`, `--root`,
`--no-cache`) as `parser.add_argument(...)` passed into the app.

**Caveat.** `argparse`'s `version` action prints to stdout and exits 0; your current
`-v` error path (when metadata is missing) printed to stderr and exited 1. The
version above degrades to `mr-manager unknown` and exits 0 instead — simpler and
fine for a TUI, but if you want to keep the non-zero exit on missing metadata, keep
a thin custom action. Update the `tests`/README if behavior changes. You can then
delete `handle_version_flag` (keep `get_installed_version`).

---

## 9. Replace (or document) the hand-rolled config format (🟡 D.3)

**Why.** `_parse_user_config_yaml` (`core/user_config.py:45-80`) accepts only a
narrow YAML subset (two-space block mapping, no flow style, no lists, no tabs). A
user editing `config.yaml` by hand with otherwise-valid YAML gets a `ValueError`,
and the accepted subset is undocumented.

**How — option A (recommended): switch to TOML.** `tomllib` is stdlib (read-only,
3.11+ — aligns with §1), robust, and a better fit for flat settings. Move the file
to `~/.config/mr-manager/config.toml`:

```toml
[discovery]
root_path = "/Users/you/code"
cache_ttl_hours = 24
```

```python
import tomllib

def load_user_config(config_path: Path | None = None) -> UserConfig:
    resolved = config_path or get_user_config_path()
    if not resolved.exists():
        return get_default_user_config()
    data = tomllib.loads(resolved.read_text(encoding="utf-8"))
    discovery = data.get("discovery", {})
    return UserConfig(
        discovery_cache_ttl_hours=_validate_discovery_cache_ttl_hours(
            str(discovery.get("cache_ttl_hours", "")), key_name="discovery.cache_ttl_hours"
        ),
        discovery_root=_validate_discovery_root(discovery.get("root_path")),
    )
```

For *writing*, `tomllib` is read-only; emit TOML by hand (your settings are flat, so
this stays trivial — atomic-write the formatted string per
`SECURITY_REMEDIATION_GUIDE.md` §1) or add the tiny `tomli-w` dependency.

**Migration caveat.** You ship `config.yaml` today (and v1.0.1 just stabilized its
keys per the CHANGELOG). Switching formats is a breaking change: detect a legacy
`config.yaml`, read it once with the old parser, write the new `config.toml`, and
optionally leave the old file with a deprecation note. Bump the minor version and
note it in `CHANGELOG.md`.

**How — option B (no format change): document the subset.** If you'd rather not
migrate, add a header comment when you write the file and a README block stating the
exact accepted format (two-space indent, `key: value`, no flow/lists/tabs, quoting
rules). Lower effort, but you keep a fragile parser.

---

## 10. Review-before-save (🟡 D.4)

**Why.** `save` writes after only a counts summary. A preview reduces mistakes,
especially once bulk-toggle (§5) lands.

**How.** Before `_controller.save_changes()` in `action_save`, build a diff and show
it in the existing `ActionModal` (it already takes a free-form `message`):

```python
def _build_save_preview(self) -> str:
    to_add = sorted(self._controller.repos_to_add(), key=lambda r: str(r).lower())
    to_remove = sorted(self._controller.repos_to_remove(), key=lambda r: str(r).lower())
    lines = []
    if to_add:
        lines.append(f"Add ({len(to_add)}):")
        lines += [f"  + {p}" for p in to_add[:10]]
        if len(to_add) > 10:
            lines.append(f"  …and {len(to_add) - 10} more")
    if to_remove:
        lines.append(f"Remove ({len(to_remove)}):")
        lines += [f"  - {p}" for p in to_remove[:10]]
        if len(to_remove) > 10:
            lines.append(f"  …and {len(to_remove) - 10} more")
    return "\n".join(lines) or "No changes."
```

Show it with confirm = "Save", cancel = "Back", and only call `save_changes()` on
confirm. For very long lists, prefer a scrollable modal over truncation — but the
truncated summary is a fine first cut.

**Caveat.** Keep the existing "Saved / Quit" modal flow afterward; this just inserts
a confirmation step ahead of the write. Don't double-prompt — gate the preview
behind `has_unsaved_changes()`.

---

## 11. Docs & smaller polish (🔵 E / F)

- **README additions:** the config-file format (§9), discovery-root narrowing (§6),
  and "requires a modern Unicode terminal" (the `●○◐◌` bullets and accent color
  assume it). Confirm and mention that **arrow keys** work alongside `j/k`
  (`OptionList` provides them) so users don't think only Vim keys are supported.
- **More actionable errors:** the scan-status label truncates long errors. For
  config-parse failures, include the offending key/line — your parser already raises
  `f"Invalid config line: {raw_line}"`, so surface that text rather than a generic
  "Config Load Failed".
- **Untrack `.idea/`** (also in the security guide): `git rm -r --cached .idea` and
  add `.idea/` to `.gitignore`.
- **Optional "run `mr` after save":** offer (behind a config flag) to run
  `mr update` / `mr register` after a successful save, closing the loop instead of
  leaving the user to switch tools. Scope decision — keep it opt-in and use the
  list-arg `subprocess` pattern, never `shell=True`.

---

## Suggested order of work

1. **§1 (Python floor)** and **§8 (argparse CLI)** — trivial, high adoption payoff.
2. **§2 (tests)** — do early; it backstops everything after.
3. **§3 (XDG path)** — correctness for a real user segment.
4. **§4 (filter) → §5 (bulk) → §10 (review-before-save)** — the headline UX arc; do
   them together since they interact (visible-set semantics).
5. **§6/§7 (discovery config + skip reporting)** — quality-of-life + speed.
6. **§9 (TOML/docs)** and **§11 (docs/polish)** — finish.

§1–§8 and §10 are mostly self-contained; §4/§5/§10 share the "operate on the visible
set" model change, so land that refactor once and build the three features on top.
