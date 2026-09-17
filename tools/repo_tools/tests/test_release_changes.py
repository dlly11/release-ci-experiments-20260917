"""Reduced CI requires an exact release transform, not filenames or author identity."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from repo_tools.release_changes import CONFIG, MANIFEST, release_branch, release_changes


@pytest.fixture
def release_tree(repository: Path, monkeypatch: pytest.MonkeyPatch, git: Callable[..., str]):
    monkeypatch.chdir(repository)
    config = repository / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"packages": {".": {"release-type": "simple", "package-name": "sample"}}})
    )
    (repository / MANIFEST).write_text('{".": "1.2.3"}\n')
    (repository / "CHANGELOG.md").write_text("# Changelog\n\n## 1.2.3\n\nOld entry.\n")
    (repository / "uv.lock").write_text("""version = 1
[[package]]
name = "sample-template"
version = "1.2.3"
source = { virtual = "." }
[[package]]
name = "sample-core"
version = "1.2.3"
source = { editable = "python/packages/core" }
[[package]]
name = "external"
version = "9.0.0"
source = { registry = "https://pypi.org/simple" }
wheels = [{ url = "https://example.invalid/file.whl", hash = "sha256:123" }]
""")
    git("init", "--initial-branch=main")
    git("add", ".")
    git("commit", "-m", "chore: initialize")
    base = git("rev-parse", "HEAD")
    for name in [
        "version.txt",
        "pyproject.toml",
        "python/packages/core/pyproject.toml",
        "CMakeLists.txt",
        "uv.lock",
        MANIFEST,
    ]:
        path = repository / name
        path.write_text(path.read_text().replace("1.2.3", "1.3.0"))
    changelog = repository / "CHANGELOG.md"
    changelog.write_text(
        changelog.read_text().replace(
            "# Changelog\n\n", "# Changelog\n\n## [1.3.0](url) (2026-09-17)\n\nNew entry.\n\n"
        )
    )
    git("commit", "-am", "chore(main): release 1.3.0")
    return repository, base, git("rev-parse", "HEAD"), git


def test_release_only(release_tree):
    root, base, head, _ = release_tree
    assert release_changes(root, base, head)[0]


@pytest.mark.parametrize(
    "name,old,new",
    [
        ("pyproject.toml", 'version = "1.3.0"', 'version = "1.3.0" # changed comment'),
        ("pyproject.toml", 'name = "sample-template"', 'name = "other"'),
        ("python/packages/core/pyproject.toml", "1.3.0", "1.2.3"),
        ("CMakeLists.txt", "LANGUAGES C", "LANGUAGES C CXX"),
        ("uv.lock", "9.0.0", "10.0.0"),
        ("uv.lock", "sha256:123", "sha256:456"),
        ("uv.lock", "https://pypi.org/simple", "https://example.invalid/simple"),
        ("uv.lock", 'editable = "python/packages/core"', 'editable = "elsewhere"'),
        ("uv.lock", 'version = "1.3.0"', 'version = "1.2.3"'),
        (MANIFEST, "1.3.0", "1.4.0"),
        ("version.txt", "1.3.0", "1.2.3"),
        ("version.txt", "1.3.0", "1.3.0-rc1"),
        ("CHANGELOG.md", "Old entry.", "Rewritten history."),
        ("CHANGELOG.md", "1.3.0", "1.4.0"),
        (CONFIG, "sample", "other"),
    ],
)
def test_unexpected_edits_use_full(release_tree, name, old, new):
    root, base, _, git = release_tree
    path = root / name
    path.write_text(path.read_text().replace(old, new))
    git("commit", "-am", "fix: unexpected edit")
    valid, reason = release_changes(root, base, git("rev-parse", "HEAD"))
    assert not valid
    assert reason


@pytest.mark.parametrize("change", ["add", "delete", "mode", "source", "symlink"])
def test_tree_changes_use_full(release_tree, change):
    root, base, _, git = release_tree
    path = root / "python/packages/core/src/sample_core/__init__.py"
    if change == "add":
        (root / "new.py").write_text("# new source\n")
    elif change == "delete":
        path.unlink()
    elif change == "mode":
        git("update-index", "--chmod=+x", "version.txt")
    elif change == "symlink":
        path.unlink()
        path.symlink_to("../../../../../../outside")
    else:
        path.write_text("# changed source\n")
    if change != "mode":
        git("add", "--all")
    git("commit", "-m", "fix: change tree")
    assert not release_changes(root, base, git("rev-parse", "HEAD"))[0]


@pytest.mark.parametrize(
    "package,suffix",
    [
        ({"package-name": "renamed-project"}, "--components--renamed-project"),
        (
            {"package-name": "name", "component": "custom", "include-component-in-tag": False},
            "--components--custom",
        ),
        ({}, ""),
    ],
)
def test_branch_configuration(package, suffix):
    assert (
        release_branch({"packages": {".": {"release-type": "simple", **package}}})
        == "release-please--branches--main" + suffix
    )


@pytest.mark.parametrize(
    "config",
    [
        [],
        {"packages": None},
        {"packages": {".": None}},
        {"packages": {"a": {"release-type": "simple"}}},
        {"packages": {".": {"release-type": "node"}}},
        {"packages": {".": {"release-type": "simple", "pull-request-title-pattern": "custom"}}},
        {"packages": {".": {"release-type": "simple", "package-name": "bad/name"}}},
        {"packages": {".": {"release-type": "simple"}}, "plugins": ["node-workspace"]},
    ],
)
def test_unsupported_branch_configuration(config):
    with pytest.raises(ValueError):
        release_branch(config)


def test_classifier_executes_base_code(release_tree):
    """A head edit cannot supply its own reduced-CI classification."""
    import shutil

    from repo_tools.ci_validation import trusted_changes

    root, base, head, git = release_tree
    assert not trusted_changes(root, base, head)[0]
    tooling = Path(__file__).resolve().parents[1]
    shutil.copytree(
        tooling / "src", root / "tools/repo_tools/src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copyfile(tooling / "run.py", root / "tools/repo_tools/run.py")
    git("add", ".")
    git("commit", "-m", "feat: add classifier")
    baseline = git("rev-parse", "HEAD")
    # This replacement would incorrectly report true if the head's classifier ran.
    classifier = root / "tools/repo_tools/src/repo_tools/commands/check_ci_context.py"
    classifier.write_text('raise AssertionError("head code must never execute")\n')
    git("commit", "-am", "fix: change classifier")
    valid, reason = trusted_changes(root, baseline, git("rev-parse", "HEAD"))
    assert not valid
    assert reason == "release version must increase"
