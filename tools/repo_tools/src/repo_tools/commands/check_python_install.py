"""Build distributions and smoke-test each wheel in its own clean environment."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from email.parser import BytesParser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from repo_tools.python_smoke_checks import INSTALL_CHECK, SMOKE_CHECKS, SmokeCheck, SmokeCommand
from repo_tools.repository_metadata import normalized_name, project_metadata, python_projects


def collect_wheels(directory: Path, expected: dict[str, str]) -> dict[str, Path]:
    """Require exactly one wheel for each expected distribution and version."""
    wheels: dict[str, Path] = {}
    for path in sorted(directory.glob("*.whl")):
        with ZipFile(path) as archive:
            metadata_files = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                raise ValueError(f"{path.name}: expected one wheel METADATA file")
            metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
        name = normalized_name(str(metadata.get("Name", "")))
        version = str(metadata.get("Version", ""))
        if name not in expected or expected[name] != version:
            raise ValueError(f"{path.name}: unexpected distribution/version {name}=={version}")
        if name in wheels:
            raise ValueError(f"{name}: multiple wheels found")
        wheels[name] = path.resolve()
    missing = expected.keys() - wheels.keys()
    if missing:
        raise ValueError(f"missing wheels: {', '.join(sorted(missing))}")
    return wheels


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    status: int = 0,
    stdout: str | None = None,
    stderr_contains: str | None = None,
    timeout: int = 300,
) -> None:
    """Run a command and include its output in any failure report."""
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"command {subprocess.list2cmdline(command)} timed out after {timeout}s; "
            f"stdout: {error.stdout!r}; stderr: {error.stderr!r}"
        ) from error
    if (
        result.returncode != status
        or (stdout is not None and result.stdout != stdout)
        or (stderr_contains is not None and stderr_contains not in result.stderr)
    ):
        raise RuntimeError(
            f"command {subprocess.list2cmdline(command)}\n"
            f"expected exit {status}, got {result.returncode}; "
            f"expected stdout {stdout!r}, stderr containing {stderr_contains!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def check_wheel(
    uv: str,
    name: str,
    version: str,
    wheel: Path,
    constraints: Path,
    temporary: Path,
    project_root: Path | None = None,
    *,
    smoke: SmokeCheck | None = None,
) -> None:
    """Install only this wheel and its declared dependencies, then exercise it."""
    env = dict(os.environ)
    for variable in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(variable, None)
    env.update(PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1")
    environment = temporary / name
    run(
        [uv, "venv", "--python", sys.executable, str(environment)],
        cwd=temporary,
        env=env,
    )
    bin_directory = environment / ("Scripts" if os.name == "nt" else "bin")
    python = str(bin_directory / ("python.exe" if os.name == "nt" else "python"))
    run(
        [uv, "pip", "install", "--python", python, "-c", str(constraints), str(wheel)],
        cwd=project_root or Path.cwd(),
        env=env,
    )
    run([uv, "pip", "check", "--python", python], cwd=temporary, env=env)
    smoke = SMOKE_CHECKS[name] if smoke is None else smoke
    run(
        [python, "-I", "-c", INSTALL_CHECK + smoke.example, name, smoke.namespace, version],
        cwd=temporary,
        env=env,
        timeout=10,
    )
    for command in smoke.commands:
        executable = bin_directory / (command.executable + (".exe" if os.name == "nt" else ""))
        run(
            [str(executable), *command.arguments],
            cwd=temporary,
            env=env,
            status=command.status,
            stdout=command.stdout,
            stderr_contains=command.stderr_contains,
            timeout=10,
        )


def check_tooling(uv: str, project_root: Path, temporary: Path) -> None:
    """Build and install private tooling separately from the released workspace wheels."""
    project = Path("tools/repo_tools/pyproject.toml")
    name, version = project_metadata(project_root, project)
    print(f"Building and checking installed private {name}=={version}", flush=True)
    dist = temporary / "tooling-dist"
    run(
        [uv, "build", str(project_root / project.parent), "--out-dir", str(dist)],
        cwd=project_root,
        env=dict(os.environ),
    )
    wheels = collect_wheels(dist, {name: version})
    constraints = temporary / "tooling-wheels.txt"
    constraints.write_text(f"{name} @ {wheels[name].as_uri()}\n", encoding="utf-8")
    check_wheel(
        uv,
        name,
        version,
        wheels[name],
        constraints,
        temporary,
        project_root,
        smoke=SmokeCheck(
            "repo_tools",
            "from repo_tools.cli import build_parser\nassert build_parser().prog == 'repo-tools'\n",
            commands=(
                SmokeCommand("repo-tools", ("--help",)),
                SmokeCommand("python", ("-I", "-m", "repo_tools", "--help")),
                SmokeCommand("repo-tools", ("--project-root", str(project_root), "check-versions")),
            ),
        ),
    )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    parser.add_argument(
        "--dist", type=Path, help="verify existing release wheels without rebuilding"
    )


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Build once and check every wheel without using the workspace environment."""
    project_root = root
    context = "build"
    try:
        uv = shutil.which("uv")
        if uv is None:
            raise ValueError("uv is required; see docs/workstation.md")
        expected = dict(
            project_metadata(project_root, path)
            for path in python_projects(project_root)
            if path != Path("pyproject.toml")
        )
        if expected.keys() != SMOKE_CHECKS.keys():
            raise ValueError(
                "workspace distributions and SMOKE_CHECKS must cover the same packages"
            )
        with tempfile.TemporaryDirectory(prefix="python-install-check-") as directory:
            temporary = Path(directory).resolve()
            dist = args.dist.resolve() if args.dist is not None else temporary / "dist"
            if args.dist is None:
                print("Building all wheels and source distributions", flush=True)
                run(
                    [uv, "build", "--all-packages", "--out-dir", str(dist)],
                    cwd=project_root,
                    env=dict(os.environ),
                )
            wheels = collect_wheels(dist, expected)
            constraints = temporary / "workspace-wheels.txt"
            constraints.write_text(
                "".join(f"{name} @ {wheel.as_uri()}\n" for name, wheel in wheels.items()),
                encoding="utf-8",
            )
            for name, wheel in wheels.items():
                context = name
                print(f"Checking installed {name}=={expected[name]}", flush=True)
                check_wheel(uv, name, expected[name], wheel, constraints, temporary, project_root)
            if args.dist is None:
                context = "private tooling"
                check_tooling(uv, project_root, temporary)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, BadZipFile) as error:
        print(f"Python install check failed ({context}): {error}", file=sys.stderr)
        return 1
    print("All Python wheels passed isolated installation checks")
    return 0
