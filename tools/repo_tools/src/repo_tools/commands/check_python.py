"""Type-check workspace members separately, then private tooling and its tests."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_tools.repository_metadata import python_projects


def check_projects(root: Path) -> None:
    """Type-check discovered deliverables, then the orchestration code."""
    for path in python_projects(root):
        if path == Path("pyproject.toml"):
            continue
        project = root / path.parent
        print(f"==> ty check {path.parent}", flush=True)
        subprocess.run(["ty", "check", "--project", str(project)], cwd=root, check=True)
    print("==> ty check private tooling (including tests)", flush=True)
    tooling = [root / "tools/repo_tools"]
    subprocess.run(
        ["ty", "check", "--project", str(root), *(str(path) for path in tooling)],
        cwd=root,
        check=True,
    )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Run the workspace type checks."""
    try:
        check_projects(root)
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Python type check failed: {error}", file=sys.stderr)
        return 1
    return 0
