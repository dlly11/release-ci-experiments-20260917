"""Build the complete Python and native API documentation site."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from repo_tools.environment import check_environment


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Generate Doxygen XML and build warning-free Sphinx HTML."""
    check_environment(root, group="docs", command="build-docs")
    build_root = root / "build/docs"
    required_tools = ("cmake", "doxygen", "ninja")
    tools = {tool: shutil.which(tool) for tool in required_tools}
    missing_tools = [tool for tool, path in tools.items() if path is None]
    if missing_tools:
        print(
            f"documentation build failed: missing tools: {', '.join(missing_tools)}",
            file=sys.stderr,
        )
        return 1

    if build_root.exists():
        shutil.rmtree(build_root)
    build_root.mkdir(parents=True)

    try:
        subprocess.run(
            [
                str(tools["cmake"]),
                "-S",
                str(root),
                "-B",
                str(build_root / "native"),
                "-G",
                "Ninja",
                "-DBUILD_TESTING=OFF",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [str(tools["doxygen"]), str(root / "tools/doxygen/Doxyfile")],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "sphinx",
                "-W",
                "--keep-going",
                "-b",
                "html",
                "-c",
                str(root / "tools/sphinx"),
                str(root),
                str(build_root / "html"),
            ],
            cwd=root,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        return error.returncode

    print(f"documentation written to {build_root / 'html'}")
    return 0
