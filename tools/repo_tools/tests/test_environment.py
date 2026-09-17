"""Real isolated interpreters must resolve sources from the selected checkout."""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Literal
from unittest.mock import Mock

import pytest

from repo_tools import cli, environment
from repo_tools.commands import check_coverage
from repo_tools.context import resolve_root


@pytest.fixture
def python_environment(
    repository: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    # A custom location ensures the check uses imports, not a hard-coded .venv path.
    directory = tmp_path_factory.mktemp("custom python environment")
    venv.EnvBuilder(with_pip=False).create(directory)
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = Path(
        subprocess.check_output(
            [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
    )
    tooling = repository / "tools/repo_tools"
    (tooling / "src/repo_tools").mkdir(parents=True)
    (tooling / "pyproject.toml").write_text('[project]\nname = "monorepo-repo-tools"\n')
    # Inspecting locations must not execute any first-party package initializer.
    for path in (
        repository / "python/packages/core/src/sample_core/__init__.py",
        tooling / "src/repo_tools/__init__.py",
    ):
        path.write_text('raise AssertionError("preflight imported project code")\n')
    (site / "sources.pth").write_text(
        f"{repository / 'python/packages/core/src'}\n{tooling / 'src'}\n", encoding="utf-8"
    )
    for name in ("sphinx", "breathe", "myst_parser", "furo", "pytest", "pytest_cov", "gcovr"):
        (site / f"{name}.py").write_text('raise AssertionError("preflight imported a tool")\n')
    (site / "sphinxcontrib").mkdir()
    (site / "sphinxcontrib/mermaid.py").write_text(
        'raise AssertionError("preflight imported an extension")\n'
    )
    monkeypatch.setattr(environment.sys, "executable", str(python))
    monkeypatch.setattr(check_coverage.platform, "system", lambda: "Linux")
    return repository, site


@pytest.mark.parametrize("group", ["docs", "coverage"])
def test_custom_environment_resolves_sources_without_importing_them(
    python_environment: tuple[Path, Path], group: Literal["docs", "coverage"]
) -> None:
    root, _ = python_environment
    environment.check_environment(root, group=group, command="check")


def test_symlinked_checkout(python_environment: tuple[Path, Path], tmp_path: Path) -> None:
    root, _ = python_environment
    alias = tmp_path / "checkout alias with spaces"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("creating directory symlinks is unavailable")
    environment.check_environment(resolve_root(alias), group="docs", command="build-docs")


def test_documentation_parent_initializer_is_not_executed(
    python_environment: tuple[Path, Path],
) -> None:
    root, site = python_environment
    (site / "sphinxcontrib/__init__.py").write_text(
        'raise AssertionError("preflight imported the parent package")\n'
    )
    environment.check_environment(root, group="docs", command="build-docs")


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "missing",
    [
        ("sphinx",),
        ("breathe",),
        ("myst_parser",),
        ("sphinxcontrib.mermaid",),
        ("sphinxcontrib",),
        ("furo",),
        ("breathe", "furo"),
    ],
)
def test_missing_documentation_dependencies_preserve_outputs(
    python_environment: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing: bool,
    missing: tuple[str, ...],
) -> None:
    root, site = python_environment
    output = root / "build/docs"
    if existing:
        output.mkdir(parents=True)
        (output / "previous.html").write_bytes(b"Previous documentation\r\n")
    before = {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
    for name in missing:
        if name == "sphinxcontrib":
            shutil.rmtree(site / name)
        else:
            (site / (name.replace(".", "/") + ".py")).unlink()
    native_tools = Mock(side_effect=AssertionError("must fail before native tool checks"))
    monkeypatch.setattr(shutil, "which", native_tools)
    assert cli.main(["--project-root", str(root), "build-docs"]) == 1
    native_tools.assert_not_called()
    assert output.exists() == existing
    assert before == {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
    error = capsys.readouterr().err
    for name in missing:
        expected = "sphinxcontrib.mermaid" if name == "sphinxcontrib" else name
        assert f"missing Python module: {expected}" in error
    assert "uv sync --locked --all-packages --group docs" in error
    assert "uv run --no-sync repo-tools build-docs" in error


@pytest.mark.parametrize("command,group", [("build-docs", "docs"), ("check-coverage", "coverage")])
@pytest.mark.parametrize(
    "problem", ["other_checkout", "missing_source", "wrong_tooling", "missing_tool"]
)
def test_bad_environment_preserves_outputs_and_explains_recovery(
    python_environment: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    group: str,
    problem: str,
) -> None:
    root, site = python_environment
    output = root / "build" / group / "previous.txt"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"Previous results\r\n")
    if problem == "missing_tool":
        (site / ("sphinx.py" if group == "docs" else "pytest_cov.py")).unlink()
    else:
        (site / "sources.pth").unlink()
        if problem == "wrong_tooling":
            (site / "sources.pth").write_text(f"{root / 'python/packages/core/src'}\n")
            (site / "repo_tools.py").touch()
        elif problem == "other_checkout":
            (site / "sample_core.py").touch()
    # Neither cwd nor PYTHONPATH may rescue an incorrectly installed environment.
    monkeypatch.setenv("PYTHONPATH", str(root / "python/packages/core/src"))
    assert cli.main(["--project-root", str(root), command]) == 1
    assert output.read_bytes() == b"Previous results\r\n"
    assert list(output.parent.iterdir()) == [output]
    error = capsys.readouterr().err
    assert "Python environment does not match" in error
    assert f"uv sync --locked --all-packages --group {group}" in error
    assert f"uv run --no-sync repo-tools {command}" in error


@pytest.mark.parametrize(
    "command,modules", [("build-docs", ["sphinx"]), ("check-coverage", ["pytest", "gcovr"])]
)
def test_commands_use_verified_interpreter_without_path_tools(
    python_environment: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    modules: list[str],
) -> None:
    root, site = python_environment
    for name in modules:
        (site / f"{name}.py").write_text('print("correct interpreter")\n')
    # Exercise the real Python tools, substituting only the unrelated native stages.
    run = subprocess.run
    executed = []

    def run_tool(arguments: list[str], **kwargs):
        if arguments[0] == sys.executable:
            if arguments[1:3] == ["-I", "-m"]:
                executed.append(arguments[3])
            return run(arguments, **kwargs)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr("shutil.which", lambda tool: f"/native/{tool}")
    monkeypatch.setattr(subprocess, "run", run_tool)
    assert cli.main(["--project-root", str(root), command]) == 0
    assert executed == modules
