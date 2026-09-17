"""Workstation diagnostics must be actionable and independent of the host tools."""

import subprocess

import pytest

from repo_tools import cli
from repo_tools.commands import doctor


@pytest.mark.parametrize(
    ("output", "status", "expected"),
    [
        ("cmake version 3.24.9", 0, False),
        ("cmake version 3.25.0", 0, True),
        ("cmake version 4.4.2", 1, False),
        ("unknown", 0, False),
        ("", 0, False),
    ],
)
def test_version_and_exit_checks(
    monkeypatch: pytest.MonkeyPatch,
    output: str,
    status: int,
    expected: bool,
) -> None:
    module = doctor
    monkeypatch.setattr(module.shutil, "which", lambda _: "/tools/cmake")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], status, output, ""),
    )
    ok, message = module.probe(module.Tool("CMake", ("cmake",), (3, 25)))
    assert ok is expected
    assert "/tools/cmake" in message


def test_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    module = doctor
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    ok, message = module.probe(module.Tool("Ninja", ("ninja",)))
    assert not ok
    assert "install it or fix PATH" in message


@pytest.mark.parametrize(
    "error", [OSError("cannot execute"), subprocess.TimeoutExpired("tool", 10)]
)
def test_probe_errors(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    module = doctor
    monkeypatch.setattr(module.shutil, "which", lambda _: "/tools/ninja")

    def fail(*args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == 10
        raise error

    monkeypatch.setattr(module.subprocess, "run", fail)
    ok, message = module.probe(module.Tool("Ninja", ("ninja",)))
    assert not ok
    assert str(error) in message


def test_compiler_overrides_and_coverage_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    module = doctor
    monkeypatch.setenv("CC", 'ccache "custom clang"')
    monkeypatch.setenv("CXX", "custom-clang++")
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    native = {tool.name: tool.command for tool in module.profile_tools("native")}
    assert native["C compiler (CC)"] == ("ccache", "custom clang")
    assert native["C++ compiler (CXX)"] == ("custom-clang++",)
    coverage = {tool.name: tool.command for tool in module.profile_tools("coverage")}
    assert coverage["gcc"] == ("gcc",)
    assert coverage["g++"] == ("g++",)


def test_compiler_path_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    module = doctor
    path = r"C:\Program Files\LLVM\bin\clang.exe"
    monkeypatch.setenv("CC", path)
    monkeypatch.setattr(module.shutil, "which", lambda value: path if value == path else None)
    assert module.compiler_command("CC", "gcc") == (path,)


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize(("profile", "expected"), [("all", 0), ("coverage", 1)])
def test_unsupported_coverage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    system: str,
    profile: str,
    expected: int,
) -> None:
    module = doctor
    arguments = ["doctor", "--profile", profile]
    monkeypatch.setattr(module.platform, "system", lambda: system)
    monkeypatch.setattr(module, "probe", lambda tool: (True, tool.name))
    assert cli.main(arguments) == expected
    assert ("SKIP" if profile == "all" else "FAIL") in capsys.readouterr().out
    assert not any(tool.gcc for tool in module.profile_tools(profile))


@pytest.mark.parametrize("compiler", ["", '"unterminated'])
def test_all_missing_tools_are_reported(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    compiler: str,
) -> None:
    module = doctor
    arguments = ["doctor", "--profile", "analysis"]
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    monkeypatch.setenv("CC", compiler)
    assert cli.main(arguments) == 1
    output = capsys.readouterr().out
    for name in ("CMake", "Ninja", "clang-format", "clang-tidy", "cppcheck"):
        assert f"FAIL {name}" in output


def test_coverage_rejects_clang_named_gcc(monkeypatch: pytest.MonkeyPatch) -> None:
    module = doctor
    monkeypatch.setattr(module.shutil, "which", lambda _: "/tools/gcc")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "clang version 21.1.8", ""),
    )
    ok, message = module.probe(module.Tool("gcc", ("gcc",), gcc=True))
    assert not ok
    assert "coverage requires the GNU GCC toolchain" in message


def test_old_python_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = doctor
    arguments = ["doctor", "--profile", "python"]
    monkeypatch.setattr(module.sys, "version_info", (3, 11))
    monkeypatch.setattr(module, "probe", lambda tool: (True, tool.name))
    assert cli.main(arguments) == 1
    assert "FAIL Python" in capsys.readouterr().out
