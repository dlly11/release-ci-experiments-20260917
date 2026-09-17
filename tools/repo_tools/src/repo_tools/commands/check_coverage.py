"""Generate and enforce coverage reports for the Python and native components."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from repo_tools.environment import check_environment


def run_check(label: str, command: list[str], *, root: Path) -> int:
    """Run one coverage stage and return its exit status."""
    print(f"==> {label}", flush=True)
    return subprocess.run(command, cwd=root, check=False).returncode


def percentage(covered: int, total: int) -> float:
    """Return a coverage percentage, treating an empty metric as complete."""
    return 100.0 if total == 0 else covered * 100.0 / total


def python_metrics(report_root: Path) -> tuple[float, float, float] | None:
    """Read Python line, branch, and aggregate coverage percentages."""
    path = report_root / "python/coverage.json"
    if not path.exists():
        return None
    totals = json.loads(path.read_text(encoding="utf-8"))["totals"]
    return (
        percentage(totals["covered_lines"], totals["num_statements"]),
        percentage(totals["covered_branches"], totals["num_branches"]),
        totals["percent_covered"],
    )


def native_metrics(report_root: Path) -> tuple[float, float] | None:
    """Read native line and branch coverage percentages."""
    path = report_root / "native/summary.json"
    if not path.exists():
        return None
    summary = json.loads(path.read_text(encoding="utf-8"))
    return summary["line_percent"], summary["branch_percent"]


def write_summary(failures: list[str], report_root: Path) -> None:
    """Write a GitHub-compatible Markdown summary for available reports."""
    python = python_metrics(report_root)
    native = native_metrics(report_root)
    rows = [
        "# Coverage summary",
        "",
        "| Stack | Lines | Branches | Aggregate |",
        "| --- | ---: | ---: | --- |",
    ]

    if python is None:
        rows.append("| Python | unavailable | unavailable | unavailable |")
    else:
        line, branch, aggregate = python
        rows.append(f"| Python | {line:.1f}% | {branch:.1f}% | {aggregate:.1f}% |")

    if native is None:
        rows.append("| Native C | unavailable | unavailable | — |")
    else:
        line, branch = native
        rows.append(f"| Native C | {line:.1f}% | {branch:.1f}% | — |")

    rows.extend(["", "Thresholds: `pyproject.toml` and `tools/coverage/gcovr.cfg`."])
    if failures:
        rows.extend(["", f"Failed stages: {', '.join(failures)}."])
    else:
        rows.extend(["", "All coverage tests and thresholds passed."])

    (report_root / "summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    parser.add_argument(
        "--cpputest-source",
        type=Path,
        metavar="PATH",
        help="use extracted local CppUTest sources without downloading (relative to cwd)",
    )


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Run both coverage suites and retain every report that can be generated."""
    if platform.system() != "Linux":
        print("coverage checks failed: native coverage requires Linux and GCC", file=sys.stderr)
        print(
            "No fresh results generated; existing coverage reports are unchanged.", file=sys.stderr
        )
        return 1
    build_root = root / "build/coverage"
    configure = ["cmake", "--preset", "coverage"]
    if args.cpputest_source is not None:
        source = args.cpputest_source.resolve()
        if not (source / "CMakeLists.txt").is_file():
            raise ValueError(
                f"--cpputest-source must contain CMakeLists.txt: {source}. "
                "Existing coverage reports are unchanged."
            )
        if source.is_relative_to(build_root.resolve()):
            raise ValueError(
                f"--cpputest-source must be outside the cleaned coverage directory: {source}. "
                "Existing coverage reports are unchanged."
            )
        configure.extend(
            [f"-DFETCHCONTENT_SOURCE_DIR_CPPUTEST={source}", "-DFETCHCONTENT_FULLY_DISCONNECTED=ON"]
        )
    check_environment(root, group="coverage", command="check-coverage")
    report_root = build_root / "reports"
    python_report_root = report_root / "python"
    native_report_root = report_root / "native"
    required_tools = ("cmake", "ctest", "ninja", "gcc", "g++", "gcov")
    missing_tools = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing_tools:
        print(f"coverage checks failed: missing tools: {', '.join(missing_tools)}", file=sys.stderr)
        print(
            "No fresh results generated; existing coverage reports are unchanged.", file=sys.stderr
        )
        return 1

    if build_root.exists():
        shutil.rmtree(build_root)
    python_report_root.mkdir(parents=True)
    native_report_root.mkdir(parents=True)
    failures: list[str] = []

    python_status = run_check(
        "Python tests and coverage",
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            f"--cov-report=json:{python_report_root / 'coverage.json'}",
            f"--cov-report=xml:{python_report_root / 'coverage.xml'}",
            f"--cov-report=html:{python_report_root / 'html'}",
        ],
        root=root,
    )
    if python_status != 0:
        failures.append("Python coverage")

    configure_status = run_check("Configure native coverage", configure, root=root)
    if configure_status != 0:
        failures.append("native configuration")
    else:
        build_status = run_check(
            "Build native coverage", ["cmake", "--build", "--preset", "coverage"], root=root
        )
        if build_status != 0:
            failures.append("native build")
        else:
            test_status = run_check(
                "Run native coverage tests", ["ctest", "--preset", "coverage"], root=root
            )
            if test_status != 0:
                failures.append("native tests")

            gcovr_status = run_check(
                "Generate and enforce native coverage",
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "gcovr",
                    "--config",
                    "tools/coverage/gcovr.cfg",
                    "--object-directory",
                    str(build_root / "native"),
                    "--cobertura-pretty",
                    "--cobertura",
                    str(native_report_root / "coverage.xml"),
                    "--html-details",
                    str(native_report_root / "index.html"),
                    "--json-summary-pretty",
                    "--json-summary",
                    str(report_root / "native/summary.json"),
                ],
                root=root,
            )
            if gcovr_status != 0:
                failures.append("native coverage")

    write_summary(failures, report_root)
    if failures:
        print(f"coverage checks failed: {', '.join(failures)}", file=sys.stderr)
        return 1

    print(f"coverage reports written to {report_root}")
    return 0
