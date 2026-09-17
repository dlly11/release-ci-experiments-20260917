"""Diagnose workstation prerequisites without installing or changing anything."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROFILES = ("python", "native", "analysis", "docs", "coverage", "all")
PROBE_TIMEOUT = 10


@dataclass(frozen=True)
class Tool:
    """An executable to probe and any known minimum version."""

    name: str
    command: tuple[str, ...]
    minimum: tuple[int, ...] = ()
    gcc: bool = False


def compiler_command(variable: str, default: str) -> tuple[str, ...]:
    """Honor compiler paths and launcher arguments without invoking a shell."""
    value = os.environ.get(variable, default)
    if executable := shutil.which(value):
        return (executable,)
    try:
        parts = shlex.split(value, posix=os.name != "nt")
    except ValueError:
        # Let the ordinary missing-executable diagnostic report malformed overrides.
        parts = [value]
    if not parts:
        parts = [value]
    return tuple(part.strip('"') if os.name == "nt" else part for part in parts)


def profile_tools(profile: str) -> list[Tool]:
    """Select system tools; Python dependency groups are installed by uv sync."""
    tools: list[Tool] = []
    if profile in ("python", "docs", "coverage", "all"):
        tools.append(Tool("uv", ("uv",), (0, 10, 9)))
    if profile != "python":
        tools.extend([Tool("CMake", ("cmake",), (3, 25)), Tool("Ninja", ("ninja",))])
    if profile in ("native", "analysis", "docs", "all"):
        default = "clang" if platform.system() == "Darwin" else "gcc"
        tools.append(Tool("C compiler (CC)", compiler_command("CC", default)))
        if profile != "docs":
            tools.append(
                Tool(
                    "C++ compiler (CXX)",
                    compiler_command("CXX", default + "++" if default == "clang" else "g++"),
                )
            )
    if profile in ("analysis", "all"):
        tools.extend(Tool(name, (name,)) for name in ("clang-format", "clang-tidy", "cppcheck"))
    if profile in ("docs", "all"):
        tools.append(Tool("Doxygen", ("doxygen",), (1, 9, 2)))
    if profile in ("coverage", "all") and platform.system() == "Linux":
        # This preset explicitly selects gcc/g++, independently of CC/CXX.
        tools.extend(Tool(name, (name,), gcc=True) for name in ("gcc", "g++", "gcov"))
    return tools


def probe(tool: Tool) -> tuple[bool, str]:
    """Return a diagnostic, including missing, failing, or stalled executables."""
    executable = shutil.which(tool.command[0])
    if executable is None:
        return False, f"{tool.name}: {tool.command[0]!r} not found; install it or fix PATH"
    command = [executable, *tool.command[1:], "--version"]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"{tool.name}: {executable}: {error}"
    output = (result.stdout + "\n" + result.stderr).strip()
    version_line = next(
        (line.strip() for line in output.splitlines() if re.search(r"\d+\.\d+", line)),
        output.splitlines()[0] if output else "no version output",
    )
    description = f"{tool.name}: {executable}: {version_line}"
    if result.returncode != 0:
        return False, f"{description} (exit {result.returncode})"
    if not output:
        return False, description
    if tool.minimum:
        match = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?", output)
        version = tuple(int(part or 0) for part in match.groups()) if match else ()
        if not version or version[: len(tool.minimum)] < tool.minimum:
            minimum = ".".join(map(str, tool.minimum))
            return False, f"{description}; requires >= {minimum} (version missing or too old)"
    if tool.gcc and ("gcc" not in output.lower() or "clang" in output.lower()):
        return False, f"{description}; coverage requires the GNU GCC toolchain"
    return True, description


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    parser.add_argument("--profile", choices=PROFILES, default="all")


def execute(args: argparse.Namespace, *, root: Path | None = None) -> int:
    """Report all prerequisites for the selected workflow and a summary status."""
    failures = 0

    def report(ok: bool, message: str) -> None:
        nonlocal failures
        failures += not ok
        print(f"{'OK' if ok else 'FAIL'} {message}")

    report(
        sys.version_info >= (3, 12),
        f"Python: {sys.executable}: {platform.python_version()} (requires >= 3.12)",
    )
    if args.profile in ("coverage", "all") and platform.system() != "Linux":
        message = "native coverage requires Linux and GCC"
        if args.profile == "coverage":
            report(False, message)
        else:
            print(f"SKIP {message}")
    for tool in profile_tools(args.profile):
        report(*probe(tool))
    print(f"{failures} prerequisite problem(s). See docs/workstation.md for setup and validation.")
    print("Python packages are managed by uv sync; compiler feature support is checked by CMake.")
    return int(failures != 0)
