"""Preserve coverage output when prerequisites prevent a new run."""

import json
import shutil
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from repo_tools import cli
from repo_tools.commands import check_coverage


@pytest.fixture
def coverage(repository: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    module = check_coverage
    monkeypatch.setattr(module, "check_environment", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    return module, repository / "build/coverage"


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
@pytest.mark.parametrize("existing", [False, True])
def test_unsupported_platform_fails_before_probes_or_output_changes(
    coverage: tuple[ModuleType, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    system: str,
    existing: bool,
) -> None:
    module, build = coverage
    if existing:
        build.mkdir(parents=True)
        (build / "previous.html").write_bytes(b"Previous results\r\n")
    before = {path: path.read_bytes() for path in build.rglob("*") if path.is_file()}
    monkeypatch.setattr(module.platform, "system", lambda: system)
    probe = Mock(side_effect=AssertionError("must reject the platform before probing"))
    monkeypatch.setattr(module, "check_environment", probe)
    monkeypatch.setattr(module.shutil, "which", probe)
    monkeypatch.setattr(module.subprocess, "run", probe)
    assert cli.main(["check-coverage"], default_root=build.parents[1]) == 1
    probe.assert_not_called()
    assert build.exists() == existing
    assert before == {path: path.read_bytes() for path in build.rglob("*") if path.is_file()}
    error = capsys.readouterr().err
    assert "native coverage requires Linux and GCC" in error
    assert "existing coverage reports are unchanged" in error


@pytest.mark.parametrize("existing", [False, True])
def test_missing_prerequisites_leave_outputs_untouched(
    coverage: tuple[ModuleType, Path],
    existing: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module, build = coverage
    reports = build / "reports"
    if existing:
        reports.mkdir(parents=True)
        (reports / "summary.md").write_bytes(b"Previous passing results\r\n")
        (reports / "report.html").write_bytes(b"Previous report\n")
    before = {path: path.read_bytes() for path in build.rglob("*") if path.is_file()}
    monkeypatch.setattr(module.shutil, "which", lambda tool: None if tool == "gcov" else tool)
    run = Mock()
    monkeypatch.setattr(module.subprocess, "run", run)
    assert cli.main(["check-coverage"], default_root=build.parents[1]) == 1
    assert before == {path: path.read_bytes() for path in build.rglob("*") if path.is_file()}
    assert build.exists() == existing
    output = capsys.readouterr().err
    assert "missing tools: gcov" in output
    assert "No fresh results generated" in output
    assert "existing coverage reports are unchanged" in output
    run.assert_not_called()


@pytest.mark.parametrize("failed", [False, True])
def test_successful_preflight_replaces_old_reports_and_reports_stage_results(
    coverage: tuple[ModuleType, Path],
    monkeypatch: pytest.MonkeyPatch,
    failed: bool,
) -> None:
    module, build = coverage
    reports = build / "reports"
    reports.mkdir(parents=True)
    previous = reports / "old.html"
    previous.write_text("old report", encoding="utf-8")
    monkeypatch.setattr(module.shutil, "which", lambda tool: tool)
    labels = []

    def run_check(label: str, command: list[str], *, root: Path) -> int:
        assert not previous.exists()
        assert (reports / "python").is_dir()
        assert (reports / "native").is_dir()
        labels.append(label)
        if label == "Configure native coverage":
            assert command == ["cmake", "--preset", "coverage"]
        if label == "Python tests and coverage":
            ((reports / "python") / "coverage.json").write_text(
                '{"totals":{"covered_lines":1,"num_statements":1,"covered_branches":0,'
                '"num_branches":0,"percent_covered":100}}',
                encoding="utf-8",
            )
            return int(failed)
        if label == "Generate and enforce native coverage":
            ((reports / "native") / "summary.json").write_text(
                '{"line_percent":100,"branch_percent":100}',
                encoding="utf-8",
            )
        return 0

    monkeypatch.setattr(module, "run_check", run_check)
    assert cli.main(["check-coverage"], default_root=build.parents[1]) == int(failed)
    assert "Generate and enforce native coverage" in labels
    summary = (reports / "summary.md").read_text()
    assert "100.0%" in summary
    assert (
        "Failed stages: Python coverage." if failed else "All coverage tests and thresholds passed."
    ) in summary


@pytest.mark.parametrize("problem", ["missing", "file", "no_cmake", "inside_output", "symlink"])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_cpputest_source_preserves_outputs(
    coverage: tuple[ModuleType, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    problem: str,
    existing: bool,
) -> None:
    module, build = coverage
    root = build.parents[1]
    if existing:
        build.mkdir(parents=True)
        (build / "previous.html").write_bytes(b"Previous reports\r\n")
    source = root / "local CppUTest"
    if problem == "file":
        source.touch()
    elif problem == "no_cmake":
        source.mkdir()
    elif problem in {"inside_output", "symlink"}:
        target = build / "native/cpputest-src"
        target.mkdir(parents=True)
        (target / "CMakeLists.txt").touch()
        if problem == "symlink":
            try:
                source.symlink_to(target, target_is_directory=True)
            except OSError:
                pytest.skip("creating directory symlinks is unavailable")
        else:
            source = target
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    existed = build.exists()
    probe = Mock(side_effect=AssertionError("must validate the source before probing"))
    monkeypatch.setattr(module, "check_environment", probe)
    monkeypatch.setattr(module.subprocess, "run", probe)
    assert cli.main(["check-coverage", "--cpputest-source", str(source)], default_root=root) == 1
    probe.assert_not_called()
    assert before == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert build.exists() == existed
    error = capsys.readouterr().err
    assert "--cpputest-source" in error
    assert "coverage reports are unchanged" in error


def test_local_cpputest_is_reapplied_to_clean_cmake_configurations(
    coverage: tuple[ModuleType, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("cmake") is None or shutil.which("ninja") is None:
        pytest.skip("CMake and Ninja are needed to verify disconnected configuration")
    module, build = coverage
    root = build.parents[1]
    cmake_module = Path(__file__).resolve().parents[3] / "cmake/CppUTest.cmake"
    # The tiny local dependency exercises the real FetchContent override without downloading.
    source = root / "approved CppUTest"
    source.mkdir()
    (source / "CMakeLists.txt").write_text("add_library(CppUTest INTERFACE)\n", encoding="utf-8")
    (root / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.25)\nproject(offline_check LANGUAGES NONE)\n"
        "if(NOT FETCHCONTENT_SOURCE_DIR_CPPUTEST OR NOT FETCHCONTENT_FULLY_DISCONNECTED)\n"
        '  message(FATAL_ERROR "Must configure without downloads")\nendif()\n'
        f'include("{cmake_module.as_posix()}")\nmonorepo_add_cpputest()\n',
        encoding="utf-8",
    )
    (root / "CMakePresets.json").write_text(
        json.dumps(
            {
                "version": 6,
                "configurePresets": [
                    {
                        "name": "coverage",
                        "generator": "Ninja",
                        "binaryDir": "${sourceDir}/build/coverage/native",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    caller = root / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    monkeypatch.setattr(module.shutil, "which", lambda tool: tool)
    original = module.run_check
    configured = []

    def stage(label: str, command: list[str], *, root: Path) -> int:
        if label == "Configure native coverage":
            assert not (build / "old-cache-marker").exists()
            status = original(label, command, root=root)
            configured.append(status)
            return status
        return 0

    monkeypatch.setattr(module, "run_check", stage)
    for _ in range(2):
        build.mkdir(parents=True, exist_ok=True)
        (build / "old-cache-marker").touch()
        assert (
            cli.main(
                [
                    "--project-root",
                    str(root),
                    "check-coverage",
                    "--cpputest-source",
                    "../approved CppUTest",
                ]
            )
            == 0
        )
        cache = (build / "native/CMakeCache.txt").read_text()
        assert f"FETCHCONTENT_SOURCE_DIR_CPPUTEST:UNINITIALIZED={source}" in cache
        assert "FETCHCONTENT_FULLY_DISCONNECTED:BOOL=ON" in cache
        assert (source / "CMakeLists.txt").read_text() == "add_library(CppUTest INTERFACE)\n"
    assert configured == [0, 0]
