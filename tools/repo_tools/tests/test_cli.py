"""Every command must parse help and reject unknown arguments before doing work."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_tools.cli import COMMANDS

LAUNCHER = Path(__file__).resolve().parents[1] / "run.py"


@pytest.mark.parametrize("command", COMMANDS, ids=str)
@pytest.mark.parametrize("argument,status", [("--help", 0), ("--unknown-option", 2)])
def test_cli_parses_before_effects(
    command: str, argument: str, status: int, tmp_path: Path
) -> None:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}
    result = subprocess.run(
        [sys.executable, "-I", str(LAUNCHER), command, argument],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == status, result.stderr
    assert "usage:" in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("entry", ["console", "module", "launcher"])
def test_usage_errors_name_the_subcommand(entry: str, tmp_path: Path) -> None:
    if entry == "console":
        executable = shutil.which("repo-tools")
        assert executable is not None
        command = [executable]
    elif entry == "module":
        command = [sys.executable, "-I", "-m", "repo_tools"]
    else:
        command = [sys.executable, "-I", "-S", str(LAUNCHER)]
    result = subprocess.run(
        [*command, "set-version", "invalid"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "usage: repo-tools set-version" in result.stderr
    assert "__main__.py" not in result.stderr
    assert list(tmp_path.iterdir()) == []
