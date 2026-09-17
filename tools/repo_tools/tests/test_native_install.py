"""Installed header and test-dependency validation."""

from pathlib import Path

import pytest

from repo_tools import cli
from repo_tools.commands import check_native_install


@pytest.fixture
def installation(
    tmp_path: Path,
) -> Path:
    checker = check_native_install
    for relative_path, prefix in checker.COMPONENTS.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(checker.expected_definitions(prefix, "1.2.3")) + "\n", encoding="utf-8"
        )
    return tmp_path


def test_valid_installation(
    installation: Path,
) -> None:
    assert check_native_install.install_errors(installation, "1.2.3") == []


@pytest.mark.parametrize(
    "defect", ["missing_header", "missing_macro", "stale_string", "stale_number"]
)
def test_invalid_version_header(
    defect: str,
    installation: Path,
) -> None:
    header = installation / "include/release_lab/core_version.h"
    if defect == "missing_header":
        header.unlink()
    else:
        contents = header.read_text(encoding="utf-8")
        if defect == "missing_macro":
            contents = contents.replace("#define RELEASE_LAB_CORE_VERSION_MAJOR 1\n", "")
        elif defect == "stale_string":
            contents = contents.replace('"1.2.3"', '"1.2.2"')
        else:
            contents = contents.replace("VERSION_PATCH 3", "VERSION_PATCH 2")
        header.write_text(contents, encoding="utf-8")
    errors = check_native_install.install_errors(installation, "1.2.3")
    assert len(errors) == 1
    assert "core_version.h" in errors[0]


def test_cpputest_content_is_rejected(
    installation: Path,
) -> None:
    library = installation / "lib/libCppUTest.a"
    library.parent.mkdir()
    library.touch()
    errors = check_native_install.install_errors(installation, "1.2.3")
    assert len(errors) == 1
    assert "test-only CppUTest content was installed" in errors[0]


@pytest.mark.parametrize("argument", ["--version", "Ada"])
@pytest.mark.parametrize("defect", ["exit", "stdout", "stderr", "timeout", "execution"])
def test_cli_failures(
    installation: Path,
    monkeypatch: pytest.MonkeyPatch,
    argument: str,
    defect: str,
) -> None:
    import subprocess

    checker = check_native_install
    executable = (
        installation
        / "bin"
        / (
            "release-lab-package-a-cli.exe"
            if checker.os.name == "nt"
            else "release-lab-package-a-cli"
        )
    )
    executable.parent.mkdir()
    executable.touch()

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert Path(command[0]) == executable.resolve()
        assert kwargs["timeout"] == 10
        output = (
            "release-lab-package-a-cli 1.2.3\n" if command[1] == "--version" else "Hello, Ada!\n"
        )
        if command[1] != argument:
            return subprocess.CompletedProcess(command, 0, output, "")
        if defect == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        if defect == "execution":
            raise OSError("cannot execute")
        return subprocess.CompletedProcess(
            command,
            int(defect == "exit"),
            "incorrect\n" if defect == "stdout" else output,
            "unexpected error" if defect == "stderr" else "",
        )

    monkeypatch.setattr(checker.subprocess, "run", run)
    errors = checker.cli_errors(installation, "1.2.3")
    assert len(errors) == 1
    assert argument in errors[0]


def test_headers_without_executable_are_not_a_complete_installation(
    installation: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    (installation / "pyproject.toml").write_text("[tool.uv.workspace]\nmembers = []\n")
    (installation / "version.txt").write_text("1.2.3\n")
    arguments = ["check-native-install", str(installation)]
    assert cli.main(arguments, default_root=installation) == 1
    assert "missing installed executable" in capsys.readouterr().err


def test_successful_installed_cli(
    installation: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    checker = check_native_install
    executable = (
        installation
        / "bin"
        / (
            "release-lab-package-a-cli.exe"
            if checker.os.name == "nt"
            else "release-lab-package-a-cli"
        )
    )
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            "release-lab-package-a-cli 1.2.3\n" if command[1] == "--version" else "Hello, Ada!\n",
            "",
        ),
    )
    assert checker.cli_errors(installation, "1.2.3") == []
