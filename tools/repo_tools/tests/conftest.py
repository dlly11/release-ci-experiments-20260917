"""Isolated fixtures for private repository tooling."""

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from repo_tools import github_checks
from repo_tools.commands import check_merge, check_release_readiness


@pytest.fixture(autouse=True)
def isolated_ci_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep simulated CI outcomes out of the test runner's real job summary."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@pytest.fixture
def repository(
    tmp_path: Path,
) -> Path:
    (tmp_path / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text(
        "project(example VERSION 1.2.3 LANGUAGES C)\n", encoding="utf-8"
    )
    packages = []
    projects = {
        Path("pyproject.toml"): "sample-template",
        Path("python/packages/core/pyproject.toml"): "sample-core",
    }
    for path, name in projects.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'[project]\nname = "{name}"\nversion = "1.2.3"\n', encoding="utf-8")
        packages.append(f'[[package]]\nname = "{name}"\nversion = "1.2.3"\n')
    with (tmp_path / "pyproject.toml").open("a") as file:
        file.write('[tool.uv.workspace]\nmembers = ["python/packages/*"]\n')
    package = tmp_path / "python/packages/core/src/sample_core"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    (tmp_path / "uv.lock").write_text("\n".join(packages), encoding="utf-8")
    return tmp_path


REPOSITORY = "owner/project"


@pytest.fixture
def git(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Callable[..., str]:
    """Run Git without inherited identities, configuration, signing, hooks, or templates."""
    for name in os.environ:
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(tmp_path_factory.mktemp("empty-git-template")))

    def run(*arguments: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Repository tests",
                "-c",
                "user.email=tests@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "tag.gpgsign=false",
                *arguments,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    return run


@pytest.fixture(params=["squash", "merge", "rebase"])
def merge_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    git: Callable[..., str],
) -> tuple[ModuleType, dict[str, Any]]:
    module = github_checks
    cli = check_merge
    policy = module.load_policy(root=Path.cwd())
    # Historical schema-1 evidence must be checked against the policy it tested.
    full = policy.pop("validation")["full"]
    policy["protection"]["required_status_checks"]["checks"] = [
        {"context": name, "app_id": 15368} for name in [*full, "Conventional PR title"]
    ]
    policy_file = tmp_path / module.POLICY
    policy_file.parent.mkdir(parents=True)
    policy_file.write_text(json.dumps(policy), encoding="utf-8")
    (tmp_path / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.uv.workspace]\nmembers = []\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)

    git("init", "--initial-branch=main")
    git("config", "user.name", "Merge tests")
    git("config", "user.email", "merge@example.invalid")
    source = tmp_path / "source.txt"
    source.write_text("before\n", encoding="utf-8")
    git("add", "source.txt", str(module.POLICY))
    git("commit", "-m", "chore: initialize")
    base = git("rev-parse", "HEAD")
    source.write_text("after\n", encoding="utf-8")
    git("commit", "-am", "fix: change contents")
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    parents = ["-p", base]
    if request.param == "merge":
        # Preserve multiple commits; only their final integrated tree was tested.
        head = git("commit-tree", tree, "-p", head, "-m", "docs: explain the change")
        parents.extend(["-p", head])
    merge = git("commit-tree", tree, *parents, "-m", "fix: change contents (#1)")
    integration = [merge]
    if request.param == "rebase":
        # GitHub preserves messages but rewrites committer metadata and SHAs.
        original_first = head
        source.write_text("final rebased contents\n", encoding="utf-8")
        git("commit", "-am", "feat: complete the change")
        head = git("rev-parse", "HEAD")
        tree = git("rev-parse", "HEAD^{tree}")
        with monkeypatch.context() as replay:
            replay.setenv("GIT_COMMITTER_DATE", "2001-01-01T00:00:00Z")
            first = git(
                "commit-tree",
                git("rev-parse", f"{original_first}^{{tree}}"),
                "-p",
                base,
                "-m",
                "fix: change contents",
            )
            merge = git("commit-tree", tree, "-p", first, "-m", "feat: complete the change")
        integration = [first, merge]
    git("update-ref", "refs/heads/main", merge)
    required = {
        check["context"]
        for check in module.load_policy(root=Path.cwd())["protection"]["required_status_checks"][
            "checks"
        ]
    } - {"Conventional PR title"}
    pr = {
        "number": 1,
        "merged_at": "2026-09-15T00:00:00Z",
        "merge_commit_sha": merge,
        "head": {"sha": head, "ref": "topic", "repo": {"full_name": REPOSITORY}},
        "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
    }
    run = {
        "id": 100,
        "workflow_id": 42,
        "path": ".github/workflows/ci.yml",
        "status": "completed",
        "conclusion": "success",
        "event": "pull_request",
        "head_sha": head,
        "head_branch": "topic",
        "repository": {"full_name": REPOSITORY},
        "pull_requests": [],
    }
    state: dict[str, Any] = {
        "arguments": ["check-merge", "--base", base, "--head", merge],
        "method": request.param,
        "base": base,
        "head": head,
        "merge": merge,
        "integration": integration,
        "tree": tree,
        "pr": pr,
        "runs": [run],
        "candidates": [pr],
        "required": required,
        "git": git,
        "jobs": [
            {"name": name, "status": "completed", "conclusion": "success"} for name in required
        ],
        "evidence": {
            "schema": 1,
            "repository": REPOSITORY,
            "run_id": 100,
            "head_sha": head,
            "checkout_sha": head,
            "tree_sha": tree,
        },
    }

    def api(endpoint: str) -> dict[str, Any]:
        if endpoint.endswith("/pulls/1"):
            return state["pr"]
        if endpoint.endswith("/workflows/ci.yml"):
            return {"id": 42}
        return next(run for run in state["runs"] if endpoint.endswith(f"/runs/{run['id']}"))

    def items(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
        if "/commits/" in endpoint:
            sha = endpoint.split("/commits/", 1)[1].split("/", 1)[0]
            if sha not in {*state["integration"], state["pr"]["merge_commit_sha"]}:
                return []
            return state["candidates"]
        return state["jobs"] if key == "jobs" else state["runs"]

    monkeypatch.setattr(module, "api", api)
    monkeypatch.setattr(cli, "api", api)
    monkeypatch.setattr(module, "items", items)
    monkeypatch.setattr(module, "validation_record", lambda *args: state["evidence"])

    return module, state


@pytest.fixture
def recovery_context(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModuleType, dict[str, Any]]:
    merge, state = merge_context
    release = check_release_readiness
    state["runs"][0].update(
        event="workflow_dispatch",
        head_branch="main",
        head_sha=state["merge"],
        head_repository={"full_name": REPOSITORY},
    )
    state["evidence"].update(head_sha=state["merge"], checkout_sha=state["merge"])
    state["current"] = state["merge"]
    state["event"] = {"inputs": {"recovery-run-id": "100"}}
    original = merge.api

    def api(endpoint: str) -> dict[str, Any]:
        if endpoint.endswith("/branches/main"):
            return {"commit": {"sha": state["current"]}}
        if "/runs?" in endpoint:
            assert "event=workflow_dispatch" in endpoint
            assert f"head_sha={state['merge']}" in endpoint
            return {"workflow_runs": state["runs"]}
        return original(endpoint)

    monkeypatch.setattr(release, "api", api)
    return release, state
