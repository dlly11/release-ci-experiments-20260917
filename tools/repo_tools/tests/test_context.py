"""Installed and source commands must use the selected checkout, independent of cwd."""

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tools import cli, github_checks
from repo_tools.commands import check_commits, check_coverage, set_version
from repo_tools.context import resolve_root
from repo_tools.repository_metadata import python_projects, version_errors

LAUNCHER = Path(__file__).resolve().parents[1] / "run.py"


def test_discovery_and_explicit_selection(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = repository / "directory with spaces" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert resolve_root() == repository
    assert resolve_root(repository) == repository
    # Explicit paths never silently fall back to an enclosing workspace.
    with pytest.raises(ValueError, match="--project-root"):
        resolve_root(nested)


@pytest.mark.parametrize("metadata", ["", "[tool.uv]\n", "not valid TOML", "tool = 4"])
def test_invalid_workspace_metadata(tmp_path: Path, metadata: str) -> None:
    (tmp_path / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(metadata, encoding="utf-8")
    with pytest.raises(ValueError, match="no repository workspace"):
        resolve_root(tmp_path)


@pytest.mark.parametrize("command", ["build-docs", "check-coverage", "check-workspace"])
@pytest.mark.parametrize(
    "configuration,field",
    [
        ({}, "members"),
        ({"members": "python/*"}, "members"),
        ({"members": [1]}, "members"),
        ({"members": [""]}, "members"),
        ({"members": [], "exclude": "python/*"}, "exclude"),
        ({"members": [], "exclude": [1]}, "exclude"),
        ({"members": [], "exclude": [""]}, "exclude"),
    ],
)
def test_malformed_workspace_fields_fail_without_effects(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    configuration: dict,
    field: str,
) -> None:
    path = repository / "pyproject.toml"
    path.write_text(
        "[tool.uv.workspace]\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in configuration.items()),
        encoding="utf-8",
    )
    for group in ("docs", "coverage"):
        output = repository / "build" / group
        output.mkdir(parents=True)
        (output / "previous.txt").write_bytes(b"Previous results\r\n")
    before = {path: path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    monkeypatch.setattr(check_coverage.platform, "system", lambda: "Linux")
    run = Mock(side_effect=AssertionError("must reject metadata before subprocesses"))
    monkeypatch.setattr(subprocess, "run", run)
    assert cli.main(["--project-root", str(repository), command]) == 1
    run.assert_not_called()
    assert before == {path: path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    error = capsys.readouterr().err
    assert "pyproject.toml" in error
    assert f"tool.uv.workspace.{field} must be a list of nonempty strings" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("command", ["build-docs", "check-coverage", "check-workspace"])
@pytest.mark.parametrize("field", ["members", "exclude"])
def test_absolute_workspace_globs_have_configuration_diagnostics(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    field: str,
) -> None:
    configuration = {"members": []}
    configuration[field] = [str(repository / "absolute")]
    (repository / "pyproject.toml").write_text(
        "[tool.uv.workspace]\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in configuration.items()),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_coverage.platform, "system", lambda: "Linux")
    run = Mock(side_effect=AssertionError("must reject the glob before subprocesses"))
    monkeypatch.setattr(subprocess, "run", run)
    assert cli.main(["--project-root", str(repository), command]) == 1
    run.assert_not_called()
    assert not (repository / "build").exists()
    error = capsys.readouterr().err
    assert "pyproject.toml" in error
    assert f"tool.uv.workspace.{field}: invalid glob" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("command", [["set-version", "2.0.0"], ["check-coverage"], ["build-docs"]])
def test_invalid_explicit_root_fails_before_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    run = Mock(side_effect=AssertionError("must not invoke a subprocess"))
    monkeypatch.setattr(subprocess, "run", run)
    assert cli.main(["--project-root", str(tmp_path), *command]) == 1
    run.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_rootless_commands_and_relative_message_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    message = tmp_path / "message with spaces.txt"
    message.write_text("fix: a standalone message\n", encoding="utf-8")
    assert cli.main(["check-pr-title", "docs: explain the command"]) == 0
    assert cli.main(["check-commits", "--message-file", message.name]) == 0
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0


def test_source_launcher_without_site_packages(repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside with spaces"
    target = tmp_path / "target with spaces"
    shutil.copytree(repository, target)
    outside.mkdir()
    # -S disables editable installs and all site-packages; -I ignores PYTHONPATH.
    for arguments in (
        ["check-versions"],
        ["--project-root", str(target), "check-versions", "--tag", "v1.2.3"],
    ):
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(LAUNCHER), *arguments],
            cwd=outside,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
    assert list(outside.iterdir()) == []


def test_explicit_root_selects_git_checkout(repository: Path, git: Callable[..., str]) -> None:
    git("init", "--initial-branch=main", str(repository))
    git("-C", str(repository), "add", ".")
    git("-C", str(repository), "commit", "-m", "fix: selected checkout")
    # Stay in the real checkout, whose history has many more commits.
    commits = check_commits.commits_between("0" * 40, "HEAD", root=repository)
    assert len(commits) == 1
    assert cli.main(["--project-root", str(repository), "check-commits", "--base", "0" * 40]) == 0


def test_selected_checkout_supplies_policy(repository: Path) -> None:
    policy = github_checks.load_policy(root=Path.cwd())
    policy["repository"]["default_branch"] = "selected-branch"
    path = repository / github_checks.POLICY
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(policy), encoding="utf-8")
    assert github_checks.load_policy(root=repository) == policy


def test_product_version_update_excludes_private_tooling(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = repository / "tools/repo_tools/pyproject.toml"
    private.parent.mkdir(parents=True)
    contents = '[project]\nname = "monorepo-repo-tools"\nversion = "0.1.0"\n'
    private.write_text(contents, encoding="utf-8")
    lock = repository / "uv.lock"
    with lock.open("a", encoding="utf-8") as file:
        file.write('[[package]]\nname = "monorepo-repo-tools"\nversion = "0.1.0"\n')

    def refresh(*args: object, **kwargs: object) -> None:
        lock.write_text(lock.read_text().replace('"1.2.3"', '"2.0.0"'), encoding="utf-8")

    monkeypatch.setattr(subprocess, "run", refresh)
    set_version.update_version(repository, "2.0.0")
    assert private.read_text() == contents
    assert 'version = "0.1.0"' in lock.read_text()
    assert private.relative_to(repository) not in python_projects(repository)
    assert version_errors(repository, "2.0.0") == []
