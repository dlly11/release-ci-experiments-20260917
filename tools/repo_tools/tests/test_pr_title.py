"""Conventional Commit subjects used by release automation."""

from types import ModuleType
from typing import Any

import pytest

from repo_tools import cli
from repo_tools.commands import check_pr_title


@pytest.mark.parametrize(
    "title, expected",
    [
        ("fix: handle invalid input", 0),
        ("feat(package-a): add output", 0),
        ("feat(core)!: replace API", 0),
        ("refactor!: remove deprecated API", 0),
        ("chore(main): release 1.2.3", 0),
        ("docs(native/core): explain buffers", 0),
        ("chore(deps): bump dependency", 0),
        ("chore(deps-dev): update tools", 0),
        ("Fix: handle input", 1),
        ("feat(): missing scope", 1),
        ("feat: ", 1),
        ("feat:   ", 1),
        ("feat:  extra leading space", 1),
        ("feat: trailing space ", 1),
        ("fix: subject\rbody", 1),
        ("fix: subject\twith tab", 1),
        ("fix: subject\u2028body", 1),
        ("feat:no space", 1),
        ("update dependencies", 1),
        ("fix: subject\nbody", 1),
        ("", 1),
    ],
)
def test_title_validation(title: str, expected: int, monkeypatch: pytest.MonkeyPatch) -> None:
    arguments = ["check-pr-title", title]
    assert cli.main(arguments) == expected


@pytest.fixture
def pr_context(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, dict[str, Any]]:
    module = check_pr_title
    pr: dict[str, Any] = {
        "state": "open",
        "title": "fix: handle invalid input",
        "head": {"sha": "a" * 40, "ref": "topic", "repo": {"full_name": "owner/project"}},
        "base": {"repo": {"full_name": "owner/project"}},
    }
    monkeypatch.setattr(module, "api", lambda endpoint: pr)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/project")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/topic")

    return module, pr


def test_manual_title_requires_matching_branch_and_head(
    pr_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _module, _ = pr_context
    assert cli.main(PR_ARGUMENTS) == 0
    monkeypatch.setenv("GITHUB_REF", "refs/heads/other")
    assert cli.main(PR_ARGUMENTS) == 1
    monkeypatch.setenv("GITHUB_REF", "refs/tags/topic")
    assert cli.main(PR_ARGUMENTS) == 1


@pytest.mark.parametrize("change", ["sha", "closed", "invalid_title", "head_repo", "base_repo"])
def test_mismatched_pr_cannot_pass_required_check(
    pr_context: tuple[ModuleType, dict[str, Any]], change: str
) -> None:
    _module, pr = pr_context
    if change == "sha":
        pr["head"]["sha"] = "b" * 40
    elif change == "closed":
        pr["state"] = "closed"
    elif change == "invalid_title":
        pr["title"] = "Update things"
    elif change == "head_repo":
        pr["head"]["repo"]["full_name"] = "fork/project"
    else:
        pr["base"]["repo"]["full_name"] = "other/project"
    assert cli.main(PR_ARGUMENTS) == 1


def test_ordinary_fork_pr_uses_real_head_not_synthetic_merge(
    pr_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _module, pr = pr_context
    pr["head"]["repo"]["full_name"] = "fork/project"
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    assert cli.main(PR_ARGUMENTS) == 0


def test_title_api_error_fails_check(
    pr_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _ = pr_context

    def fail(endpoint: str) -> None:
        raise RuntimeError("API unavailable")

    monkeypatch.setattr(module, "api", fail)
    assert cli.main(PR_ARGUMENTS) == 1


PR_ARGUMENTS = ["check-pr-title", "--pr", "1", "--expected-head", "a" * 40]
