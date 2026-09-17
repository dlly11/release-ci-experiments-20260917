"""Read-only GitHub transport and pagination regressions."""

import subprocess

import pytest

from repo_tools import github_api


def test_github_helper_only_uses_get_and_detects_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = github_api
    commands = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert kwargs["timeout"] == 30
        output = "owner/project\n" if command[1] == "repo" else '{"name": "project"}'
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.repository_name() == "owner/project"
    assert module.api("repos/owner/project") == {"name": "project"}
    assert commands[-1] == ["gh", "api", "--method", "GET", "repos/owner/project"]


@pytest.mark.parametrize(
    "error",
    [
        OSError("missing gh"),
        subprocess.TimeoutExpired("gh", 30),
        subprocess.CalledProcessError(1, "gh", stderr="HTTP 403"),
    ],
)
def test_github_errors_are_actionable(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    module = github_api

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(module.subprocess, "run", fail)
    with pytest.raises(RuntimeError):
        module.api("repos/owner/project")


def test_collection_reads_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    module = github_api
    monkeypatch.setattr(module, "gh", lambda *args: '[[{"id":1}],[{"id":2}]]')
    assert module.items("endpoint") == [{"id": 1}, {"id": 2}]
    monkeypatch.setattr(module, "gh", lambda *args: '[{"jobs":[{"id":1}]},{"jobs":[{"id":2}]}]')
    assert module.items("endpoint", "jobs") == [{"id": 1}, {"id": 2}]
