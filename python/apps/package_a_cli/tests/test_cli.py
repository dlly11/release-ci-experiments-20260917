"""Tests for the Python Package A CLI."""

import subprocess
import sys

import pytest

from release_lab_package_a_cli import main


def test_cli_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["Ada Lovelace"]) == 0
    assert capsys.readouterr().out == "Hello, Ada Lovelace!\n"


def test_cli_accepts_custom_prefix(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--prefix", "Welcome", "Grace"]) == 0
    assert capsys.readouterr().out == "Welcome, Grace!\n"


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_cli_reports_invalid_names(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main([name])

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error: name must contain at least one non-whitespace character" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("name, status", [("Ada", 0), ("   ", 2)])
def test_module_entry_point(name: str, status: int) -> None:
    result = subprocess.run(  # noqa: S603 -- fixed interpreter/module with test input
        [sys.executable, "-m", "release_lab_package_a_cli", name],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == status
    assert result.stdout == ("Hello, Ada!\n" if status == 0 else "")
    if status == 0:
        assert result.stderr == ""
    else:
        assert "error: name must contain" in result.stderr
        assert "Traceback" not in result.stderr
