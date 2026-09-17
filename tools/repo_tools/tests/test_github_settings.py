"""Audit GitHub policy drift without allowing remote writes."""

import json
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from repo_tools import cli, github_checks
from repo_tools.commands import check_github_settings


@pytest.fixture
def settings_context(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, dict[str, Any]]:
    module = check_github_settings
    policy = module.load_policy(root=Path.cwd())
    state: dict[str, Any] = {
        "repository": deepcopy(policy["repository"]),
        "protection": deepcopy(policy["protection"]),
        "protected": True,
    }

    def api(endpoint: str) -> dict[str, Any]:
        assert endpoint.startswith("repos/owner/project")
        if endpoint.endswith("/protection"):
            return state["protection"]
        if endpoint.endswith("/branches/main"):
            return {"protected": state["protected"]}
        return state["repository"]

    monkeypatch.setattr(module, "api", api)

    return module, state


def test_match_ignores_unmanaged_fields_and_check_order(
    settings_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    _module, state = settings_context
    state["repository"]["description"] = "Unmanaged description"
    state["protection"]["required_status_checks"]["checks"].reverse()
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 0


@pytest.mark.parametrize(
    "change",
    ["merge", "merge_title", "linear", "protection", "missing", "additional", "source", "reviews"],
)
def test_reports_policy_drift(
    settings_context: tuple[ModuleType, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    change: str,
) -> None:
    _module, state = settings_context
    checks = state["protection"]["required_status_checks"]["checks"]
    if change == "merge":
        state["repository"]["allow_merge_commit"] = False
    elif change == "merge_title":
        state["repository"]["merge_commit_title"] = "MERGE_MESSAGE"
    elif change == "linear":
        state["protection"]["required_linear_history"]["enabled"] = True
    elif change == "protection":
        state["protected"] = False
    elif change == "missing":
        checks.pop()
    elif change == "additional":
        checks.append({"context": "Unexpected check", "app_id": 15368})
    elif change == "source":
        checks[0]["app_id"] = -1
    else:
        state["protection"]["required_pull_request_reviews"] = None
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 1
    assert "expected" in capsys.readouterr().err


def test_all_differences_are_reported(
    settings_context: tuple[ModuleType, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    _module, state = settings_context
    state["repository"].update(allow_merge_commit=False, allow_rebase_merge=False)
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 1
    output = capsys.readouterr().err
    assert "allow_merge_commit" in output and "allow_rebase_merge" in output


def test_api_error_is_not_reported_as_drift(
    settings_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _ = settings_context

    def fail(endpoint: str) -> None:
        raise RuntimeError("HTTP 403: missing Administration read permission")

    monkeypatch.setattr(module, "api", fail)
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 2


@pytest.mark.parametrize("contents", ["{", "{}", '{"repository": {}, "protection": {}}'])
def test_invalid_policy_is_configuration_error(
    settings_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contents: str,
) -> None:
    _module, _ = settings_context
    path = tmp_path / "policy.json"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(github_checks, "POLICY", path)
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 2


def test_duplicate_policy_checks_are_rejected(
    settings_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module, _ = settings_context
    policy = module.load_policy(root=Path.cwd())
    checks = policy["protection"]["required_status_checks"]["checks"]
    checks.append(checks[0])
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(github_checks, "POLICY", path)
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 2


@pytest.fixture
def extended_context(
    settings_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    module, state = settings_context
    state["repository"]["allow_auto_merge"] = False
    state.update(errors=[], fail="", reads=[])
    original_api = module.api

    def api(endpoint: str) -> dict[str, Any]:
        state["reads"].append(endpoint)
        if state["fail"] and state["fail"] in endpoint:
            raise RuntimeError("HTTP 403: unavailable")
        if "/actions/permissions/" in endpoint:
            return {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            }
        if "/codeowners/errors" in endpoint:
            return {"errors": state["errors"]}
        return original_api(endpoint)

    def items(endpoint: str) -> list[dict[str, Any]]:
        state["reads"].append(endpoint)
        if state["fail"] and state["fail"] in endpoint:
            raise RuntimeError("HTTP 403: unavailable")
        return [
            {
                "type": "pull_request",
                "ruleset_source_type": "Organization",
                "ruleset_source": "owner",
                "ruleset_id": 42,
                "parameters": {"required_approving_review_count": 2},
            }
        ]

    monkeypatch.setattr(module, "api", api)
    monkeypatch.setattr(module, "items", items)
    return state


def test_extended_reports_capabilities_without_enforcing_them(
    extended_context: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["check-github-settings", "--repo", "owner/project", "--extended"]) == 0
    output = capsys.readouterr().out
    assert "Repository auto-merge: disabled" in output
    assert "Organization owner" in output
    assert "not compared with classic policy" in output
    assert "Actions create/approve PRs setting: disabled" in output


def test_extended_codeowners_errors_are_problems(extended_context: dict[str, Any]) -> None:
    extended_context["errors"] = [
        {"path": ".github/CODEOWNERS", "line": 2, "message": "Unknown owner"}
    ]
    assert cli.main(["check-github-settings", "--repo", "owner/project", "--extended"]) == 1


@pytest.mark.parametrize("endpoint", ["/protection", "/rules/", "/actions/", "/codeowners/"])
def test_extended_continues_after_unavailable_endpoint(
    extended_context: dict[str, Any], capsys: pytest.CaptureFixture[str], endpoint: str
) -> None:
    extended_context["fail"] = endpoint
    assert cli.main(["check-github-settings", "--repo", "owner/project", "--extended"]) == 2
    output = capsys.readouterr()
    assert "HTTP 403" in output.err
    assert any("/rules/" in read for read in extended_context["reads"])
    assert any("/actions/" in read for read in extended_context["reads"])
    assert any("/codeowners/" in read for read in extended_context["reads"])


def test_default_does_not_read_extended_endpoints(extended_context: dict[str, Any]) -> None:
    assert cli.main(["check-github-settings", "--repo", "owner/project"]) == 0
    assert not any(
        fragment in read
        for read in extended_context["reads"]
        for fragment in ("/rules/", "/actions/", "/codeowners/")
    )
