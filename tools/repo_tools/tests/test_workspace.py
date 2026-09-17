"""Temporary workspaces exercise registration drift without running external tools."""

import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from repo_tools import cli
from repo_tools.commands import check_workspace
from repo_tools.python_smoke_checks import SmokeCheck
from repo_tools.repository_metadata import discover_members


@pytest.mark.parametrize(
    "config,field",
    [
        ({}, "tool"),
        ({"tool": 1}, "tool"),
        ({"tool": {}}, "tool.uv"),
        ({"tool": {"uv": []}}, "tool.uv"),
        ({"tool": {"uv": {}}}, "tool.uv.workspace"),
        ({"tool": {"uv": {"workspace": "invalid"}}}, "tool.uv.workspace"),
    ],
)
def test_workspace_tables_are_validated(tmp_path: Path, config: dict, field: str) -> None:
    with pytest.raises(ValueError) as failure:
        discover_members(tmp_path, config)
    assert str(failure.value) == f"{tmp_path / 'pyproject.toml'}: {field} must be a table"


@pytest.mark.parametrize("exclude", [False, True])
def test_empty_workspace_members_are_valid(tmp_path: Path, exclude: bool) -> None:
    workspace = {"members": []}
    if exclude:
        workspace["exclude"] = []
    assert discover_members(tmp_path, {"tool": {"uv": {"workspace": workspace}}}) == ([], [])


def write_root(root: Path, *, exclude: tuple[str, ...] = (), overlap: bool = False) -> None:
    members = ["python/packages/*", "python/apps/*"]
    if overlap:
        members.append("python/packages/core")
    namespaces = '["sample_core", "sample_app"]'
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample-template"\n'
        f"[tool.uv.workspace]\nmembers = {json.dumps(members)}\n"
        f"exclude = {json.dumps(exclude)}\n"
        f"[tool.coverage.run]\nsource = {namespaces}\n"
        '[tool.ruff.lint.isort]\nknown-first-party = ["sample_core", "sample_app", "repo_tools"]\n',
        encoding="utf-8",
    )


def write_member(root: Path, path: str, name: str, namespace: str) -> None:
    member = root / path
    package = member / "src" / namespace
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    (member / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n', encoding="utf-8")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    module = check_workspace
    write_root(tmp_path)
    (tmp_path / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    write_member(tmp_path, "python/packages/core", "sample-core", "sample_core")
    write_member(tmp_path, "python/apps/app", "sample-app", "sample_app")
    projects = {
        Path("pyproject.toml"): "sample-template",
        Path("python/packages/core/pyproject.toml"): "sample-core",
        Path("python/apps/app/pyproject.toml"): "sample-app",
    }
    release = tmp_path / module.RELEASE_CONFIG
    release.parent.mkdir(parents=True)
    entries = [
        {"type": "toml", "path": path.as_posix(), "jsonpath": "$.project.version"}
        for path in projects
    ]
    entries.append({"type": "generic", "path": "CMakeLists.txt"})
    release.write_text(json.dumps({"packages": {".": {"extra-files": entries}}}), encoding="utf-8")
    monkeypatch.setattr(
        module,
        "SMOKE_CHECKS",
        {"sample-core": SmokeCheck("sample_core", ""), "sample-app": SmokeCheck("sample_app", "")},
    )
    return module, tmp_path


def test_valid_workspace_is_read_only(workspace: tuple[ModuleType, Path]) -> None:
    module, root = workspace
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert module.workspace_errors(root) == []
    assert cli.main(["check-workspace"], default_root=root) == 0
    assert before == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_new_member_reports_all_missing_registrations(workspace: tuple[ModuleType, Path]) -> None:
    module, root = workspace
    write_member(root, "python/packages/new", "sample-new", "sample_new")
    errors = "\n".join(module.workspace_errors(root))
    for registry in (
        "SMOKE_CHECKS",
        "source",
        "known-first-party",
        "extra-files",
    ):
        assert registry in errors
    assert "missing sample-new" in errors
    assert "missing sample_new" in errors


@pytest.mark.parametrize("operation", ["remove", "rename"])
def test_removed_or_renamed_member_reports_stale_entries(
    workspace: tuple[ModuleType, Path], operation: str
) -> None:
    module, root = workspace
    path = root / "python/packages/core"
    if operation == "remove":
        shutil.rmtree(path)
    else:
        path.rename(root / "python/packages/renamed")
    errors = "\n".join(module.workspace_errors(root))
    assert "stale python/packages/core/pyproject.toml" in errors
    if operation == "rename":
        assert "missing python/packages/renamed/pyproject.toml" in errors


def test_distribution_rename_is_detected(workspace: tuple[ModuleType, Path]) -> None:
    module, root = workspace
    (root / "python/packages/core/pyproject.toml").write_text(
        '[project]\nname = "renamed-core"\n', encoding="utf-8"
    )
    errors = "\n".join(module.workspace_errors(root))
    assert "SMOKE_CHECKS: missing renamed-core" in errors
    assert "SMOKE_CHECKS: stale sample-core" in errors


def test_excluded_directory_and_overlapping_globs(workspace: tuple[ModuleType, Path]) -> None:
    module, root = workspace
    write_member(root, "python/packages/excluded", "ignored", "ignored")
    write_root(root, exclude=("python/packages/excluded",), overlap=True)
    assert module.workspace_errors(root) == []


@pytest.mark.parametrize(
    ("name", "namespace", "message"),
    [
        ("Sample_Core", "different", "workspace distribution names: duplicate sample-core"),
        ("different", "sample_core", "workspace import namespaces: duplicate sample_core"),
    ],
)
def test_duplicate_component_names(
    workspace: tuple[ModuleType, Path], name: str, namespace: str, message: str
) -> None:
    module, root = workspace
    write_member(root, "python/packages/duplicate", name, namespace)
    assert message in module.workspace_errors(root)


def test_namespace_rename_is_detected(workspace: tuple[ModuleType, Path]) -> None:
    module, root = workspace
    (root / "python/packages/core/src/sample_core").rename(
        root / "python/packages/core/src/new_core"
    )
    errors = "\n".join(module.workspace_errors(root))
    assert "namespace 'sample_core' is missing" in errors
    assert "source: missing new_core" in errors
    assert "known-first-party: stale sample_core" in errors


@pytest.mark.parametrize("problem", ["missing_metadata", "bad_metadata", "missing_namespace"])
def test_invalid_member_layout(workspace: tuple[ModuleType, Path], problem: str) -> None:
    module, root = workspace
    member = root / "python/packages/core"
    if problem == "missing_metadata":
        (member / "pyproject.toml").unlink()
    elif problem == "bad_metadata":
        (member / "pyproject.toml").write_text("[broken", encoding="utf-8")
    else:
        (member / "src/sample_core/__init__.py").unlink()
    assert any("python/packages/core" in error for error in module.workspace_errors(root))
    assert cli.main(["check-workspace"], default_root=root) == 1


@pytest.mark.parametrize(
    "problem", ["missing_root", "duplicate", "string_duplicate", "type", "selector", "stale"]
)
def test_release_registration_errors(workspace: tuple[ModuleType, Path], problem: str) -> None:
    module, root = workspace
    path = root / module.RELEASE_CONFIG
    config = json.loads(path.read_text(encoding="utf-8"))
    entries = config["packages"]["."]["extra-files"]
    if problem == "missing_root":
        entries.pop(0)
    elif problem == "duplicate":
        entries.append(entries[0].copy())
    elif problem == "string_duplicate":
        entries.append("pyproject.toml")
    elif problem == "stale":
        entries.append(
            {"type": "toml", "path": "deleted/pyproject.toml", "jsonpath": "$.project.version"}
        )
    elif problem == "type":
        entries[0]["type"] = "generic"
    else:
        entries[0]["jsonpath"] = "$.version"
    path.write_text(json.dumps(config), encoding="utf-8")
    errors = module.workspace_errors(root)
    assert errors
    assert all(str(module.RELEASE_CONFIG) in error for error in errors)


def test_duplicate_type_and_coverage_registrations(
    workspace: tuple[ModuleType, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, root = workspace
    path = root / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'source = ["sample_core", "sample_app"]',
            'source = ["sample_core", "sample_app", "sample_core"]',
        ),
        encoding="utf-8",
    )
    errors = "\n".join(module.workspace_errors(root))
    assert "source: duplicate sample_core" in errors


def test_malformed_root_returns_failure(
    workspace: tuple[ModuleType, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _module, root = workspace
    (root / "pyproject.toml").write_text("[broken", encoding="utf-8")
    assert cli.main(["check-workspace"], default_root=root) == 1
    assert "no repository workspace" in capsys.readouterr().err


def test_member_cannot_reuse_root_distribution_name(workspace: tuple[ModuleType, Path]) -> None:
    module, root = workspace
    write_member(root, "python/packages/duplicate", "sample-template", "different")
    assert "workspace distribution names: duplicate sample-template" in module.workspace_errors(
        root
    )
