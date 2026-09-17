"""Release automation must use explicit credentials and only the expected managed PR."""

import json
from pathlib import Path
from typing import Any

import pytest

from repo_tools import cli
from repo_tools.commands import check_release_automation as automation
from repo_tools.release_changes import CONFIG, release_branch


@pytest.mark.parametrize("mode", ["github-token", "app", "pat"])
@pytest.mark.parametrize("automatic", ["false", "true"])
def test_configuration(mode: str, automatic: str) -> None:
    environment = {
        "RELEASE_AUTH_MODE": mode,
        "RELEASE_AUTO_MERGE": automatic,
        "RELEASE_APP_CLIENT_ID": "client",
        "RELEASE_APP_PRIVATE_KEY": "key",
        "RELEASE_PAT": "pat",
    }
    if mode == "github-token" and automatic == "true":
        with pytest.raises(ValueError, match="post-merge CI"):
            automation.configuration(environment)
    else:
        assert automation.configuration(environment) == (mode, automatic == "true")


def test_default_ignores_unused_credentials() -> None:
    assert automation.configuration({}) == ("github-token", False)
    assert automation.configuration({"RELEASE_PAT": "unused"}) == ("github-token", False)


@pytest.mark.parametrize(
    "environment",
    [
        {"RELEASE_AUTH_MODE": "typo"},
        {"RELEASE_AUTO_MERGE": "yes"},
        {"RELEASE_AUTH_MODE": "pat", "RELEASE_APP_PRIVATE_KEY": "not-a-fallback"},
        {"RELEASE_AUTH_MODE": "app", "RELEASE_PAT": "not-a-fallback"},
        {"RELEASE_AUTH_MODE": "app", "RELEASE_APP_CLIENT_ID": "client"},
    ],
)
def test_invalid_configuration(environment: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        automation.configuration(environment)


@pytest.fixture
def managed_branch() -> str:
    return release_branch(json.loads(Path(CONFIG).read_text()))


@pytest.fixture
def release_pr(monkeypatch: pytest.MonkeyPatch, managed_branch: str) -> dict[str, Any]:
    pr = {
        "state": "open",
        "draft": False,
        "title": "chore(main): release 2.0.0",
        "base": {"ref": "main", "repo": {"full_name": "owner/project"}},
        "head": {
            "ref": managed_branch,
            "sha": "a" * 40,
            "repo": {"full_name": "owner/project"},
        },
        "labels": [{"name": "autorelease: pending"}],
    }
    monkeypatch.setattr(automation, "api", lambda _: pr)
    return pr


def test_major_release_is_eligible(release_pr: dict[str, Any], managed_branch: str) -> None:
    assert (
        automation.eligible_pr(
            "owner/project",
            1,
            managed_branch,
            "a" * 40,
            root=Path.cwd(),
        )
        == release_pr["title"]
    )


@pytest.mark.parametrize(
    "change", ["closed", "draft", "fork", "base", "branch", "head", "title", "label", "repo"]
)
def test_ineligible_pr(release_pr: dict[str, Any], change: str, managed_branch: str) -> None:
    if change == "closed":
        release_pr["state"] = "closed"
    elif change == "draft":
        release_pr["draft"] = True
    elif change == "fork":
        release_pr["head"]["repo"]["full_name"] = "fork/project"
    elif change == "base":
        release_pr["base"]["ref"] = "other"
    elif change == "branch":
        release_pr["head"]["ref"] = "unrelated"
    elif change == "head":
        release_pr["head"]["sha"] = "b" * 40
    elif change == "title":
        release_pr["title"] = "feat: unrelated"
    elif change == "label":
        release_pr["labels"] = []
    else:
        release_pr["base"]["repo"] = None
    with pytest.raises(ValueError):
        automation.eligible_pr(
            "owner/project",
            1,
            managed_branch,
            "a" * 40,
            root=Path.cwd(),
        )


def test_configuration_cli_checks_repository_and_writes_no_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RELEASE_AUTH_MODE", "pat")
    monkeypatch.setenv("RELEASE_AUTO_MERGE", "true")
    monkeypatch.setenv("RELEASE_PAT", "secret-value")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/project")
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(automation, "api", lambda _: {"allow_auto_merge": False})
    assert cli.main(["check-release-automation"]) == 1
    assert not output.exists()
    monkeypatch.setattr(automation, "api", lambda _: {"allow_auto_merge": True})
    assert cli.main(["check-release-automation"]) == 0
    assert output.read_text() == "auth-mode=pat\nauto-merge=true\n"


def test_pr_cli_publishes_validated_title(
    release_pr: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    managed_branch: str,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/project")
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert (
        cli.main(
            [
                "check-release-automation",
                "--pr",
                "1",
                "--branch",
                managed_branch,
                "--expected-head",
                "a" * 40,
            ]
        )
        == 0
    )
    assert output.read_text() == f"title={release_pr['title']}\n"
