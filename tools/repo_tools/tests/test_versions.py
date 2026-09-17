"""Version validation and transactional update regressions."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from repo_tools import cli, repository_metadata
from repo_tools.commands import check_python, check_versions, set_version


def snapshot(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_consistent_versions(
    repository: Path,
) -> None:
    checker = check_versions
    assert checker.repository_version(repository) == "1.2.3"
    assert checker.version_errors(repository, "1.2.3", "v1.2.3") == []


@pytest.mark.parametrize(
    "version", ["1.2", "01.2.3", "1.2.3-rc1", "garbage", "", "\u0661.\u0662.\u0663"]
)
def test_invalid_canonical_version(
    version: str,
    repository: Path,
) -> None:
    (repository / "version.txt").write_text(version, encoding="utf-8")
    with pytest.raises(ValueError, match=r"must contain X\.Y\.Z"):
        check_versions.repository_version(repository)


@pytest.mark.parametrize("relative_path", ["pyproject.toml", "CMakeLists.txt", "uv.lock"])
def test_stale_metadata(
    relative_path: str,
    repository: Path,
) -> None:
    path = repository / relative_path
    path.write_text(path.read_text(encoding="utf-8").replace("1.2.3", "1.2.2"), encoding="utf-8")
    assert any(
        relative_path in error for error in check_versions.version_errors(repository, "1.2.3")
    )


def test_missing_locked_projects(
    repository: Path,
) -> None:
    (repository / "uv.lock").write_text("package = []\n", encoding="utf-8")
    errors = check_versions.version_errors(repository, "1.2.3")
    assert len(errors) == len(repository_metadata.python_projects(repository))
    assert all("missing workspace project" in error for error in errors)


def test_wrong_tag(
    repository: Path,
) -> None:
    assert check_versions.version_errors(repository, "1.2.3", "v1.2.2") == [
        "release tag: expected v1.2.3, found v1.2.2"
    ]


def test_malformed_metadata_is_reported(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (repository / "pyproject.toml").write_text("[broken", encoding="utf-8")
    arguments = ["check-versions"]
    assert cli.main(arguments, default_root=repository) == 1
    assert "no repository workspace" in capsys.readouterr().err


def test_set_version_success(repository: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setter = set_version
    arguments = ["set-version", "2.0.0"]
    monkeypatch.setattr(setter.shutil, "which", lambda _: "/approved/bin/uv")

    def refresh_lock(*args: object, **kwargs: object) -> None:
        lock = repository / "uv.lock"
        lock.write_text(
            lock.read_text(encoding="utf-8").replace("1.2.3", "2.0.0"), encoding="utf-8"
        )

    run = Mock(side_effect=refresh_lock)
    monkeypatch.setattr(setter.subprocess, "run", run)
    assert cli.main(arguments, default_root=repository) == 0
    run.assert_called_once_with(["uv", "lock"], cwd=repository, check=True)
    assert check_versions.repository_version(repository) == "2.0.0"
    assert check_versions.version_errors(repository, "2.0.0") == []


@pytest.mark.parametrize("failure", ["lock", "validation", "declaration", "interrupt"])
def test_failed_update_restores_every_managed_file(
    failure: str,
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setter = set_version
    if failure == "declaration":
        (repository / "CMakeLists.txt").write_text("project(example)\n", encoding="utf-8")
    before = snapshot(repository)
    arguments = ["set-version", "2.0.0"]
    monkeypatch.setattr(setter.shutil, "which", lambda _: "/approved/bin/uv")

    def fail_lock(*args: object, **kwargs: object) -> None:
        (repository / "uv.lock").write_text("partial write\n", encoding="utf-8")
        if failure == "interrupt":
            raise KeyboardInterrupt
        raise subprocess.CalledProcessError(1, ["uv", "lock"])

    # Returning without refreshing the lock causes the real post-update checker to fail.
    run = Mock(side_effect=fail_lock if failure in {"lock", "interrupt"} else None)
    monkeypatch.setattr(setter.subprocess, "run", run)
    assert cli.main(arguments, default_root=repository) == (130 if failure == "interrupt" else 1)
    assert snapshot(repository) == before
    if failure == "declaration":
        run.assert_not_called()


@pytest.mark.parametrize("missing_uv", [False, True])
def test_rejected_update_does_not_write(
    missing_uv: bool,
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = snapshot(repository)
    arguments = ["set-version", "2.0.0" if missing_uv else "invalid"]
    monkeypatch.setattr(set_version.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as error:
        cli.main(arguments, default_root=repository)
    assert error.value.code == 2
    assert snapshot(repository) == before


def test_new_member_is_discovered_by_version_setter_and_type_checks(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = repository / "python/packages/added"
    namespace = member / "src/added"
    namespace.mkdir(parents=True)
    (namespace / "__init__.py").touch()
    metadata = member / "pyproject.toml"
    metadata.write_text('[project]\nname = "added"\nversion = "1.2.3"\n', encoding="utf-8")
    with (repository / "uv.lock").open("a") as lock:
        lock.write('[[package]]\nname = "added"\nversion = "1.2.3"\n')
    commands = []

    def run(command: list[str], **kwargs: object) -> None:
        commands.append(command)
        if command == ["uv", "lock"]:
            lock = repository / "uv.lock"
            lock.write_text(lock.read_text().replace("1.2.3", "2.0.0"), encoding="utf-8")

    monkeypatch.setattr(subprocess, "run", run)
    check_python.check_projects(repository)
    assert ["ty", "check", "--project", str(member)] in commands
    set_version.update_version(repository, "2.0.0")
    assert 'version = "2.0.0"' in metadata.read_text()
    assert repository_metadata.version_errors(repository, "2.0.0") == []


@pytest.mark.parametrize(
    "declaration",
    [
        "project(sample VERSION 1.2.3 LANGUAGES C)",
        'PROJECT(\n sample\n VERSION "1.2.3" # x-release-please-version\n LANGUAGES C\n)',
        'project(sample DESCRIPTION "VERSION 9.9.9 and project(fake VERSION 8.8.8)" VERSION 1.2.3)',
        "project(sample DESCRIPTION [=[) VERSION 9.9.9 (]=] VERSION [=[1.2.3]=])",
        "project(sample VERSION [[\n1.2.3]])",
        "project(sample VERSION 1.2.3)\r\n",
    ],
)
def test_cmake_version_update_only_changes_project_literal(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    declaration: str,
) -> None:
    contents = (
        "cmake_minimum_required(VERSION 3.25.1)\n"
        "# project(ignored VERSION 1.2.3)\n"
        "#[=[\nproject(also_ignored VERSION 6.6.6)\n]=]\n"
        'set(unrelated "project(fake VERSION 5.5.5)")\n' + declaration + "\n"
    )
    cmake = repository / "CMakeLists.txt"
    cmake.write_bytes(contents.encode())
    metadata = repository_metadata
    assert metadata.cmake_version(repository) == "1.2.3"

    def refresh(*args: object, **kwargs: object) -> None:
        lock = repository / "uv.lock"
        lock.write_text(lock.read_text().replace("1.2.3", "2.0.0"), encoding="utf-8")

    monkeypatch.setattr(subprocess, "run", refresh)
    set_version.update_version(repository, "2.0.0")
    assert (
        cmake.read_bytes()
        == contents.replace(declaration, declaration.replace("1.2.3", "2.0.0")).encode()
    )
    assert metadata.version_errors(repository, "2.0.0") == []


@pytest.mark.parametrize(
    "contents",
    [
        "cmake_minimum_required(VERSION 3.25.1)",
        "project(sample LANGUAGES C)",
        "project(sample VERSION)",
        "project(sample VERSION 1.2.3 VERSION 2.3.4)",
        "project(first VERSION 1.2.3)\nproject(second VERSION 1.2.3)",
        "set(v 1.2.3)\nproject(sample VERSION ${v})",
        'project(sample VERSION "${v}")',
        "project(sample VERSION 1.2)",
        "project(sample VERSION 01.2.3)",
        'project(sample VERSION"1.2.3")',
        'project(sample VERSION 1.2."3")',
        "project(sample VERSION 1.2.3",
        'project(sample VERSION "1.2.3)',
        "project(sample VERSION [[1.2.3)",
        "#[[project(sample VERSION 1.2.3)",
        ")\nproject(sample VERSION 1.2.3)",
        "project(sample VERSION (1.2.3))",
    ],
)
def test_invalid_cmake_project_is_rejected_before_any_writes(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
) -> None:
    (repository / "CMakeLists.txt").write_text(contents, encoding="utf-8")
    before = snapshot(repository)
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError, match=r"CMakeLists\.txt"):
        repository_metadata.cmake_version(repository)
    with pytest.raises(ValueError, match=r"CMakeLists\.txt"):
        set_version.update_version(repository, "2.0.0")
    assert snapshot(repository) == before
    run.assert_not_called()
