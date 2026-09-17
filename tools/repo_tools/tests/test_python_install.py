"""Regression checks for isolated wheel installation and artifact validation."""

import base64
import hashlib
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest

from repo_tools import cli
from repo_tools.commands import check_python_install
from repo_tools.python_smoke_checks import SMOKE_CHECKS, SmokeCheck


def write_wheel(
    directory: Path,
    name: str,
    *,
    version: str = "1.2.3",
    requires: str = "",
    code: str = "",
    entry_points: str = "",
) -> Path:
    """Create a small installable wheel without a build backend or network access."""
    namespace = name.replace("-", "_")
    info = f"{namespace}-{version}.dist-info"
    files = {
        f"{namespace}/__init__.py": code,
        f"{namespace}/py.typed": "",
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n{requires}",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    if entry_points:
        files[f"{info}/entry_points.txt"] = entry_points
    records = []
    for path, content in files.items():
        data = content.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        records.append(f"{path},sha256={digest},{len(data)}\n")
    files[f"{info}/RECORD"] = "".join(records) + f"{info}/RECORD,,\n"
    wheel = directory / f"{namespace}-{version}-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return wheel


@pytest.mark.parametrize("problem", ["missing", "version", "duplicate", "unexpected"])
def test_bad_artifacts_fail(tmp_path: Path, problem: str) -> None:
    module = check_python_install
    if problem == "version":
        write_wheel(tmp_path, "release-lab-core", version="0.0.1")
    elif problem == "unexpected":
        write_wheel(tmp_path, "another-package")
    elif problem == "duplicate":
        wheel = write_wheel(tmp_path, "release-lab-core")
        shutil.copyfile(wheel, tmp_path / "duplicate.whl")
    with pytest.raises(ValueError):
        module.collect_wheels(tmp_path, {"release-lab-core": "1.2.3"})


@pytest.mark.parametrize("declared", [False, True])
def test_install_uses_only_declared_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declared: bool
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is needed for the offline installation regression")
    module = check_python_install
    core = write_wheel(tmp_path, "release-lab-core", code='message = "Hello"\n')
    package = write_wheel(
        tmp_path,
        "release-lab-package-a",
        requires="Requires-Dist: release-lab-core>=1.0\n" if declared else "",
        code="from release_lab_core import message\n",
    )
    constraints = tmp_path / "constraints.txt"
    constraints.write_text(f"release-lab-core @ {core.as_uri()}\n", encoding="utf-8")
    monkeypatch.setitem(
        module.SMOKE_CHECKS,
        "release-lab-package-a",
        SmokeCheck(
            "release_lab_package_a",
            """
from release_lab_package_a import message
assert message == "Hello"
""",
        ),
    )
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_NO_CONFIG", "1")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    # A source tree on PYTHONPATH must not rescue the missing wheel dependency.
    (tmp_path / "release_lab_core").mkdir()
    (tmp_path / "release_lab_core/__init__.py").write_text('message = "Hello"\n', encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    if declared:
        module.check_wheel(uv, "release-lab-package-a", "1.2.3", package, constraints, tmp_path)
    else:
        with pytest.raises(RuntimeError, match="ModuleNotFoundError"):
            module.check_wheel(uv, "release-lab-package-a", "1.2.3", package, constraints, tmp_path)


@pytest.mark.parametrize(
    ("code", "options"),
    [("raise SystemExit(7)", {}), ('print("wrong")', {"stdout": "expected\n"})],
)
def test_failed_smoke_command_is_reported(
    tmp_path: Path, code: str, options: dict[str, str]
) -> None:
    with pytest.raises(RuntimeError, match=r"command.*python"):
        check_python_install.run(
            [sys.executable, "-I", "-c", code],
            cwd=tmp_path,
            env=dict(os.environ),
            stdout=options.get("stdout"),
        )


def test_failure_returns_nonzero_and_removes_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = check_python_install
    monkeypatch.setattr(module.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(module.shutil, "which", lambda _: "uv")

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("build failed deliberately")

    monkeypatch.setattr(module, "run", fail)
    assert cli.main(["check-python-install"]) == 1
    assert "build failed deliberately" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_release_mode_checks_supplied_wheels_without_rebuilding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = check_python_install
    wheel = write_wheel(tmp_path, "release-lab-core")
    monkeypatch.setattr(
        module, "python_projects", lambda root: {Path("core/pyproject.toml"): "release-lab-core"}
    )
    monkeypatch.setattr(
        module, "project_metadata", lambda root, path: ("release-lab-core", "1.2.3")
    )
    monkeypatch.setattr(
        module, "SMOKE_CHECKS", {"release-lab-core": SmokeCheck("release_lab_core", "")}
    )
    monkeypatch.setattr(module.shutil, "which", lambda _: "uv")

    def no_build(*args: object, **kwargs: object) -> None:
        pytest.fail("release mode must not rebuild distributions")

    checked = []

    def check(
        uv: str,
        name: str,
        version: str,
        artifact: Path,
        constraints: Path,
        temporary: Path,
        project_root: Path,
    ) -> None:
        checked.append(artifact)
        assert artifact == wheel
        assert wheel.as_uri() in constraints.read_text()

    monkeypatch.setattr(module, "run", no_build)
    monkeypatch.setattr(module, "check_tooling", no_build)
    monkeypatch.setattr(module, "check_wheel", check)
    assert cli.main(["check-python-install", "--dist", str(tmp_path)]) == 0
    assert checked == [wheel]
    assert wheel.exists()


def test_install_discovers_selected_project_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is needed for the offline installation regression")
    module = check_python_install
    project = tmp_path / "project"
    artifacts = tmp_path / "private-wheels"
    temporary = tmp_path / "isolated"
    for path in (project, artifacts, temporary):
        path.mkdir()
    write_wheel(artifacts, "private-dependency", code='message = "Private"\n')
    wheel = write_wheel(
        artifacts,
        "release-lab-core",
        requires="Requires-Dist: private-dependency==1.2.3\n",
        code="from private_dependency import message\n",
    )
    # Only this checkout's config knows where to find the private dependency.
    (project / "pyproject.toml").write_text(
        f'[tool.uv]\nno-index = true\nfind-links = ["{artifacts.as_uri()}"]\n', encoding="utf-8"
    )
    constraints = temporary / "constraints.txt"
    constraints.touch()
    monkeypatch.setitem(
        module.SMOKE_CHECKS,
        "release-lab-core",
        SmokeCheck(
            "release_lab_core",
            """
from release_lab_core import message
assert message == "Private"
""",
        ),
    )
    for variable in ("UV_NO_CONFIG", "UV_FIND_LINKS", "UV_CONFIG_FILE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    module.check_wheel(uv, "release-lab-core", "1.2.3", wheel, constraints, temporary, project)


def test_hanging_smoke_command_times_out_with_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match=r"timed out.*started"):
        check_python_install.run(
            [
                sys.executable,
                "-I",
                "-c",
                'import time; print("started", flush=True); time.sleep(30)',
            ],
            cwd=tmp_path,
            env=dict(os.environ),
            timeout=1,
        )


@pytest.mark.parametrize("problem", [None, "missing_entrypoint", "wrong_output", "wrong_status"])
def test_renamed_distribution_and_cli_retain_registered_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str | None
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is needed for the offline installation regression")
    smoke = SMOKE_CHECKS["release-lab-package-a-cli"]
    monkeypatch.setitem(
        check_python_install.SMOKE_CHECKS,
        "renamed-app",
        replace(
            smoke,
            namespace="renamed_app",
            example="",
            commands=tuple(replace(case, executable="renamed-cli") for case in smoke.commands),
        ),
    )
    code = (
        "import sys\n"
        "def main():\n"
        "    name = sys.argv[1]\n"
        "    if not name.strip():\n"
        '        print("name must contain at least one non-whitespace character", '
        "file=sys.stderr)\n"
        f"        return {5 if problem == 'wrong_status' else 2}\n"
        '    prefix = sys.argv[3] if len(sys.argv) > 2 else "Hello"\n'
        + (
            '    print("incorrect greeting")\n'
            if problem == "wrong_output"
            else '    print(f"{prefix}, {name}!")\n'
        )
    )
    wheel = write_wheel(
        tmp_path,
        "renamed-app",
        code=code,
        entry_points=""
        if problem == "missing_entrypoint"
        else "[console_scripts]\nrenamed-cli = renamed_app:main\n",
    )
    constraints = tmp_path / "constraints.txt"
    constraints.touch()
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_NO_CONFIG", "1")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    # The checks must use installed entry points independently of PATH.
    monkeypatch.setenv("PATH", "")
    if problem is None:
        check_python_install.check_wheel(uv, "renamed-app", "1.2.3", wheel, constraints, tmp_path)
    else:
        with pytest.raises((OSError, RuntimeError), match="renamed-cli"):
            check_python_install.check_wheel(
                uv, "renamed-app", "1.2.3", wheel, constraints, tmp_path
            )


def test_private_tooling_checks_are_selected_explicitly_after_a_distribution_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = check_python_install
    project = tmp_path / "tools/repo_tools/pyproject.toml"
    project.parent.mkdir(parents=True)
    project.write_text('[project]\nname = "renamed-tools"\nversion = "0.1.0"\n', encoding="utf-8")
    dist = tmp_path / "tooling-dist"
    dist.mkdir()
    write_wheel(dist, "renamed-tools", version="0.1.0")
    commands = []
    monkeypatch.setattr(module, "run", lambda command, **kwargs: commands.append(command))
    module.check_tooling("uv", tmp_path, tmp_path)
    bin_directory = tmp_path / "renamed-tools" / ("Scripts" if os.name == "nt" else "bin")
    executable = str(bin_directory / ("repo-tools.exe" if os.name == "nt" else "repo-tools"))
    python = str(bin_directory / ("python.exe" if os.name == "nt" else "python"))
    assert [executable, "--help"] in commands
    assert [python, "-I", "-m", "repo_tools", "--help"] in commands
    assert [executable, "--project-root", str(tmp_path), "check-versions"] in commands
