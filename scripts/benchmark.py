# /// script
# requires-python = ">=3.13"
# dependencies =[
#     "matplotlib",
# ]
# ///

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

RUNNER_CODE = """
import shutil
import sys
import time
from pathlib import Path

src_path = Path.cwd() / "src"
sys.path.insert(0, str(src_path if src_path.exists() else Path.cwd()))

run_type = sys.argv[1]
scan_root = Path(sys.argv[2]).expanduser()
is_cold = run_type == "cold"

cache_dir = Path.home() / ".cache" / "mr-manager"
if is_cold and cache_dir.exists():
    shutil.rmtree(cache_dir, ignore_errors=True)

try:
    from mr_manager.core.discovery import discover_git_repositories
except ImportError as exc:
    try:
        from mr_manager.discovery import discover_git_repositories
    except ImportError:
        print(f"ERR|import_discovery|{exc}")
        sys.exit(1)

has_cache = False
try:
    from mr_manager.core.cache import load_cached_repositories, save_cached_repositories
    has_cache = True
except ImportError:
    try:
        from mr_manager.cache import load_cached_repositories, save_cached_repositories
        has_cache = True
    except ImportError:
        pass

if not is_cold and not has_cache:
    print("SKIP|no_cache_module")
    sys.exit(0)

t0 = time.perf_counter()
repositories = []

if not is_cold and has_cache:
    repositories = load_cached_repositories()
    if not repositories:
        repositories = discover_git_repositories(scan_root)
        save_cached_repositories(repositories)
else:
    repositories = discover_git_repositories(scan_root)
    if has_cache:
        save_cached_repositories(repositories)

duration = time.perf_counter() - t0
print(f"OK|{duration}|{len(repositories)}")
"""


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        raise RuntimeError(f"Command failed: {command}\nstdout: {stdout}\nstderr: {stderr}")
    return result


def get_repo_root() -> Path:
    result = run_command(["git", "rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip()).resolve()


def get_current_ref(repo_root: Path) -> str:
    return run_command(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()


def _shorten_ref(ref: str) -> str:
    if len(ref) == 40 and all(char in "0123456789abcdef" for char in ref.lower()):
        return ref[:12]
    return ref


def get_current_display_label(repo_root: Path) -> str:
    branch = run_command(["git", "branch", "--show-current"], cwd=repo_root).stdout.strip()
    if branch:
        return branch
    github_head_ref = os.environ.get("GITHUB_HEAD_REF", "").strip()
    if github_head_ref:
        return github_head_ref
    github_ref_name = os.environ.get("GITHUB_REF_NAME", "").strip()
    if github_ref_name:
        return github_ref_name
    return run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root).stdout.strip()


def get_default_versions(repo_root: Path, current_ref: str, tag_limit: int | None) -> list[str]:
    tags_output = run_command(["git", "tag", "--sort=v:refname"], cwd=repo_root).stdout.strip()
    tags = tags_output.splitlines() if tags_output else []
    if tag_limit is not None and tag_limit > 0:
        tags = tags[-tag_limit:]
    versions = tags + [current_ref]
    seen: set[str] = set()
    ordered_versions: list[str] = []
    for version in versions:
        if version in seen:
            continue
        seen.add(version)
        ordered_versions.append(version)
    return ordered_versions


def sanitize_for_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * p
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    fraction = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def parse_steps(raw_steps: str | None) -> list[str]:
    if raw_steps is None:
        return ["collect", "summary", "plot"]
    normalized = [step.strip().lower() for step in raw_steps.split(",") if step.strip()]
    if "all" in normalized:
        return ["collect", "summary", "plot"]
    valid = {"collect", "summary", "plot"}
    unknown = [step for step in normalized if step not in valid]
    if unknown:
        raise ValueError(f"Unknown step(s): {', '.join(unknown)}")
    return normalized


@contextmanager
def temporary_worktree(repo_root: Path, reference: str):
    worktree_path = Path(tempfile.mkdtemp(prefix="mr-manager-benchmark-"))
    run_command(
        ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(worktree_path), reference],
    )
    try:
        yield worktree_path
    finally:
        run_command(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_path)],
            check=False,
        )


def collect_benchmark_data(
    *,
    repo_root: Path,
    versions: list[str],
    version_labels: dict[str, str],
    runs: int,
    scan_root: Path,
    run_home_root: Path,
) -> dict:
    records: list[dict[str, str | int | float]] = []
    runner_script: Path | None = None
    with temporary_worktree(repo_root, "HEAD") as worktree:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as runner_file:
            runner_file.write(RUNNER_CODE.strip())
            runner_script = Path(runner_file.name)

        try:
            print(f"Running benchmark in temporary worktree: {worktree}")
            for version_ref in versions:
                version_label = version_labels.get(version_ref, version_ref)
                print(f"\nChecking out {version_label} [{_shorten_ref(version_ref)}]...")
                run_command(["git", "checkout", "--detach", version_ref], cwd=worktree)
                version_home = run_home_root / sanitize_for_filename(version_ref)
                if version_home.exists():
                    shutil.rmtree(version_home)
                version_home.mkdir(parents=True, exist_ok=True)

                for run_type in ("cold", "warm"):
                    print(f"  Running {runs} {run_type} runs...", end=" ")
                    skipped_reason: str | None = None
                    for iteration in range(1, runs + 1):
                        env = dict(os.environ)
                        env["HOME"] = str(version_home)
                        result = run_command(
                            [sys.executable, str(runner_script), run_type, str(scan_root)],
                            cwd=worktree,
                            env=env,
                            check=False,
                        )
                        output = result.stdout.strip()
                        if output.startswith("SKIP|"):
                            skipped_reason = output.split("|", maxsplit=1)[1]
                            break
                        if not output.startswith("OK|"):
                            stderr = result.stderr.strip()
                            raise RuntimeError(
                                "Benchmark run failed for "
                                f"{version_ref} ({run_type}, #{iteration})\n"
                                f"stdout: {output}\nstderr: {stderr}"
                            )
                        _, duration_str, repo_count_str = output.split("|")
                        records.append(
                            {
                                "version": version_label,
                                "version_ref": version_ref,
                                "run_type": run_type,
                                "iteration": iteration,
                                "duration_seconds": float(duration_str),
                                "repo_count": int(repo_count_str),
                            }
                        )
                    if skipped_reason is None:
                        print("done")
                    else:
                        print(f"skipped ({skipped_reason})")
        finally:
            if runner_script is not None:
                runner_script.unlink(missing_ok=True)

    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "scan_root": str(scan_root),
        "runs": runs,
        "versions": [version_labels.get(version_ref, version_ref) for version_ref in versions],
        "version_refs": [
            {"label": version_labels.get(version_ref, version_ref), "ref": version_ref}
            for version_ref in versions
        ],
        "records": records,
    }


def build_summary(data: dict) -> str:
    records: list[dict] = data.get("records", [])
    if not records:
        return "No benchmark records available."

    grouped_durations: dict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_repos: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record in records:
        key = (str(record["version"]), str(record["run_type"]))
        grouped_durations[key].append(float(record["duration_seconds"]))
        grouped_repos[key].append(int(record["repo_count"]))

    lines = [
        "mr-manager startup benchmark summary",
        f"created_at: {data.get('created_at', '-')}",
        f"scan_root: {data.get('scan_root', '-')}",
        f"configured_runs_per_start_type: {data.get('runs', '-')}",
    ]

    version_refs = data.get("version_refs", [])
    if isinstance(version_refs, list) and version_refs:
        lines.extend(["", "Version references:"])
        for version_ref in version_refs:
            if not isinstance(version_ref, dict):
                continue
            label = str(version_ref.get("label", "-"))
            ref = str(version_ref.get("ref", "-"))
            lines.append(f"- {label}: {_shorten_ref(ref)}")

    lines.extend(
        [
            "",
            "Per-version timings:",
            (
                "version                                        start  runs  mean_ms  "
                "median_ms  p95_ms  avg_repos"
            ),
            "-" * 97,
        ],
    )

    versions: list[str] = list(data.get("versions", []))
    for version in versions:
        for run_type in ("cold", "warm"):
            key = (version, run_type)
            durations = grouped_durations.get(key, [])
            if not durations:
                continue
            avg_repos = statistics.mean(grouped_repos[key])
            lines.append(
                f"{version[:45]:45}  {run_type:5}  {len(durations):4}  "
                f"{statistics.mean(durations) * 1000:7.2f}  "
                f"{statistics.median(durations) * 1000:9.2f}  "
                f"{percentile(durations, 0.95) * 1000:6.2f}  "
                f"{avg_repos:9.1f}"
            )

    lines.extend(["", "Warm-vs-cold speedup:"])
    has_speedup = False
    for version in versions:
        cold = grouped_durations.get((version, "cold"), [])
        warm = grouped_durations.get((version, "warm"), [])
        if not cold or not warm:
            continue
        cold_mean = statistics.mean(cold)
        warm_mean = statistics.mean(warm)
        if warm_mean <= 0:
            continue
        speedup = cold_mean / warm_mean
        delta_percent = ((cold_mean - warm_mean) / cold_mean) * 100 if cold_mean > 0 else 0
        lines.append(
            f"- {version}: {speedup:.2f}x faster warm start "
            f"({delta_percent:.1f}% less startup time)"
        )
        has_speedup = True

    if not has_speedup:
        lines.append("- Not available (warm data missing for compared versions).")

    return "\n".join(lines)


def save_plot(data: dict, plot_file: Path) -> None:
    import matplotlib.pyplot as plt

    records: list[dict] = data.get("records", [])
    if not records:
        raise ValueError("No records available to plot.")

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_repos: dict[tuple[str, str], list[int]] = defaultdict(list)
    versions: list[str] = list(data.get("versions", []))

    for record in records:
        key = (str(record["version"]), str(record["run_type"]))
        grouped[key].append(float(record["duration_seconds"]))
        grouped_repos[key].append(int(record["repo_count"]))

    cold_means = [statistics.mean(grouped[(version, "cold")]) for version in versions]
    warm_means: list[float] = []
    cold_ms_per_repo: list[float] = []
    warm_ms_per_repo: list[float] = []

    for index, version in enumerate(versions):
        cold_repos = max(1.0, statistics.mean(grouped_repos[(version, "cold")]))
        cold_ms_per_repo.append((cold_means[index] / cold_repos) * 1000)

        warm_values = grouped.get((version, "warm"), [])
        if warm_values:
            warm_mean = statistics.mean(warm_values)
            warm_means.append(warm_mean)
            warm_repos = max(1.0, statistics.mean(grouped_repos[(version, "warm")]))
            warm_ms_per_repo.append((warm_mean / warm_repos) * 1000)
        else:
            warm_means.append(float("nan"))
            warm_ms_per_repo.append(float("nan"))

    x_positions = list(range(len(versions)))
    bar_width = 0.35

    fig, left_axis = plt.subplots(figsize=(11, 6))
    left_axis.bar(
        [x - bar_width / 2 for x in x_positions],
        cold_means,
        width=bar_width,
        label="Cold start mean (s)",
        color="#4ecdc4",
    )
    left_axis.bar(
        [x + bar_width / 2 for x in x_positions],
        warm_means,
        width=bar_width,
        label="Warm start mean (s)",
        color="#ff6b6b",
    )
    left_axis.set_xticks(x_positions, versions, rotation=20, ha="right")
    left_axis.set_ylabel("Duration (seconds)")
    left_axis.set_title("mr-manager startup benchmark")

    right_axis = left_axis.twinx()
    right_axis.plot(
        x_positions,
        cold_ms_per_repo,
        marker="o",
        color="#008080",
        label="Cold ms/repo",
    )
    right_axis.plot(
        x_positions,
        warm_ms_per_repo,
        marker="x",
        color="#b30000",
        linestyle="--",
        label="Warm ms/repo",
    )
    right_axis.set_ylabel("Time per repository (ms)")
    right_axis.set_ylim(bottom=0)

    left_handles, left_labels = left_axis.get_legend_handles_labels()
    right_handles, right_labels = right_axis.get_legend_handles_labels()
    left_axis.legend(left_handles + right_handles, left_labels + right_labels, loc="upper right")

    fig.tight_layout()
    plot_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_file, dpi=160)
    plt.close(fig)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark mr-manager startup across git versions.",
    )
    parser.add_argument("--runs", type=int, default=5, help="Runs per start type and version.")
    parser.add_argument("--scan-root", type=Path, default=Path.home())
    parser.add_argument(
        "--versions",
        nargs="*",
        help="Version refs to benchmark (e.g. --versions v0.0.1 main).",
    )
    parser.add_argument(
        "--tag-limit",
        type=int,
        default=5,
        help="Number of latest tags to include.",
    )
    parser.add_argument(
        "--steps",
        help="Comma-separated steps: collect,summary,plot or all (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for benchmark artifacts (default: .cache/mr-manager/benchmarks).",
    )
    parser.add_argument(
        "--benchmark-id",
        help="Artifact folder name (default: timestamp + commit).",
    )
    parser.add_argument("--data-file", type=Path, help="Raw benchmark JSON file path.")
    parser.add_argument("--summary-file", type=Path, help="Summary output file path.")
    parser.add_argument("--plot-file", type=Path, help="Plot output file path.")
    parser.add_argument(
        "--force-collect",
        action="store_true",
        help="Re-run collection even when a data file already exists.",
    )
    args = parser.parse_args()

    if args.runs <= 0:
        raise ValueError("--runs must be greater than 0.")

    repo_root = get_repo_root()
    current_ref = get_current_ref(repo_root)
    current_display_label = get_current_display_label(repo_root)
    versions = args.versions or get_default_versions(repo_root, current_ref, args.tag_limit)
    if not versions:
        raise ValueError("No versions selected for benchmarking.")
    version_labels = {version_ref: version_ref for version_ref in versions}
    if current_ref in version_labels:
        version_labels[current_ref] = f"{current_display_label} (current)"

    steps = parse_steps(args.steps)

    now_token = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    short_sha = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root).stdout.strip()
    benchmark_id = args.benchmark_id or f"{now_token}-{short_sha}"

    output_dir = args.output_dir or (repo_root / ".cache" / "mr-manager" / "benchmarks")
    run_dir = output_dir / benchmark_id
    run_dir.mkdir(parents=True, exist_ok=True)

    data_file = args.data_file or (run_dir / "data.json")
    summary_file = args.summary_file or (run_dir / "summary.txt")
    plot_file = args.plot_file or (run_dir / "plot.png")
    run_home_root = run_dir / "_run_home"

    benchmark_data: dict | None = None
    if "collect" in steps:
        if data_file.exists() and not args.force_collect:
            print(f"Reusing existing data file: {data_file}")
            benchmark_data = read_json(data_file)
        else:
            print(
                "Collecting benchmark data\n"
                f"  runs: {args.runs}\n"
                f"  scan_root: {args.scan_root.expanduser().resolve()}\n"
                "  versions: "
                f"{', '.join(version_labels.get(version, version) for version in versions)}"
            )
            benchmark_data = collect_benchmark_data(
                repo_root=repo_root,
                versions=versions,
                version_labels=version_labels,
                runs=args.runs,
                scan_root=args.scan_root.expanduser().resolve(),
                run_home_root=run_home_root,
            )
            write_json(data_file, benchmark_data)
            print(f"Saved raw data: {data_file}")
    else:
        if not data_file.exists():
            raise FileNotFoundError(
                f"Data file not found: {data_file}. Run with collect step or provide --data-file."
            )
        benchmark_data = read_json(data_file)

    if benchmark_data is None:
        raise RuntimeError("Benchmark data is unavailable.")

    if "summary" in steps:
        summary = build_summary(benchmark_data)
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(summary, encoding="utf-8")
        print(f"Saved summary: {summary_file}\n")
        print(summary)

    if "plot" in steps:
        save_plot(benchmark_data, plot_file)
        print(f"\nSaved plot: {plot_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
