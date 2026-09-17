"""Release gating must use successful push CI for the current main commit."""

import json
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from repo_tools import cli, github_checks
from repo_tools.commands import check_release_readiness

REPOSITORY = "owner/project"
SHA = "a" * 40


@pytest.fixture
def release_context(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, dict[str, Any]]:
    module = check_release_readiness
    run = {
        "id": 100,
        "workflow_id": 42,
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }
    state: dict[str, Any] = {
        "event": {"workflow_run": deepcopy(run)},
        "runs": [run],
        "head": SHA,
        "reads": [],
        "jobs": [
            {"name": "Merged PR verification", "status": "completed", "conclusion": "success"}
        ],
    }

    def api(endpoint: str) -> dict[str, Any]:
        state["reads"].append(endpoint)
        assert endpoint.startswith(f"repos/{REPOSITORY}/")
        if endpoint.endswith("/branches/main"):
            return {"commit": {"sha": state["head"]}}
        if endpoint.endswith("/workflows/ci.yml"):
            return {"id": 42}
        if "/runs?" in endpoint:
            assert f"head_sha={SHA}" in endpoint
            assert "event=push" in endpoint
            return {"workflow_runs": state["runs"]}
        return next(run for run in state["runs"] if endpoint.endswith(f"/runs/{run['id']}"))

    monkeypatch.setattr(module, "api", api)
    monkeypatch.setattr(module, "items", lambda *args: state["jobs"])
    return module, state


@pytest.mark.parametrize("event_name", ["workflow_run", "workflow_dispatch"])
def test_successful_current_push_authorizes_release(
    release_context: tuple[ModuleType, dict[str, Any]], event_name: str
) -> None:
    module, state = release_context
    assert module.ready(
        event_name, state["event"], REPOSITORY, "refs/heads/main", SHA, root=Path.cwd()
    )
    assert state["reads"].count(f"repos/{REPOSITORY}/branches/main") == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_id", 99),
        ("path", ".github/workflows/other.yml"),
        ("event", "pull_request"),
        ("event", "workflow_dispatch"),
        ("head_branch", "topic"),
        ("head_sha", "b" * 40),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", "cancelled"),
        ("conclusion", "skipped"),
        ("repository", {"full_name": "other/project"}),
        ("head_repository", {"full_name": "fork/project"}),
    ],
)
def test_latest_run_must_match_all_release_requirements(
    release_context: tuple[ModuleType, dict[str, Any]], field: str, value: object
) -> None:
    module, state = release_context
    state["runs"][0][field] = value
    with pytest.raises(ValueError, match=field):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/main", SHA, root=Path.cwd())


@pytest.mark.parametrize("field", ["event", "head_repository", "workflow_id"])
def test_automatic_event_is_checked_independently_of_latest_run(
    release_context: tuple[ModuleType, dict[str, Any]], field: str
) -> None:
    module, state = release_context
    state["event"]["workflow_run"][field] = None
    with pytest.raises(ValueError, match=field):
        module.ready(
            "workflow_run", state["event"], REPOSITORY, "refs/heads/main", SHA, root=Path.cwd()
        )


def test_stale_automatic_run_skips_but_manual_run_fails(
    release_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = release_context
    state["head"] = "b" * 40
    assert not module.ready(
        "workflow_run", state["event"], REPOSITORY, "refs/heads/main", SHA, root=Path.cwd()
    )
    with pytest.raises(ValueError, match="main is now"):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/main", SHA, root=Path.cwd())


def test_old_success_cannot_override_new_failure_or_rerun(
    release_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = release_context
    newer = deepcopy(state["runs"][0])
    newer.update(id=101, status="in_progress", conclusion=None)
    state["runs"].insert(0, newer)
    with pytest.raises(ValueError, match="status"):
        module.ready(
            "workflow_run", state["event"], REPOSITORY, "refs/heads/main", SHA, root=Path.cwd()
        )
    newer.update(status="completed", conclusion="failure")
    with pytest.raises(ValueError, match="conclusion"):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/main", SHA, root=Path.cwd())


def test_main_advance_during_reads_prevents_release(
    release_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, state = release_context
    original = module.api

    def advance(endpoint: str) -> dict[str, Any]:
        result = original(endpoint)
        if endpoint.endswith("/runs/100"):
            state["head"] = "b" * 40
        return result

    monkeypatch.setattr(module, "api", advance)
    assert not module.ready(
        "workflow_run", state["event"], REPOSITORY, "refs/heads/main", SHA, root=Path.cwd()
    )


def test_missing_ci_and_manual_non_main_are_rejected(
    release_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = release_context
    state["runs"] = []
    with pytest.raises(ValueError, match="no push CI"):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/main", SHA, root=Path.cwd())
    with pytest.raises(ValueError, match="main branch"):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/topic", SHA, root=Path.cwd())


@pytest.mark.parametrize("conclusion", ["missing", "skipped", "failure"])
def test_release_requires_actual_merge_verification(
    release_context: tuple[ModuleType, dict[str, Any]], conclusion: str
) -> None:
    module, state = release_context
    if conclusion == "missing":
        state["jobs"] = []
    else:
        state["jobs"][0]["conclusion"] = conclusion
    with pytest.raises(ValueError, match="Merged PR verification"):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/main", SHA, root=Path.cwd())


@pytest.mark.parametrize("allowed", [True, False])
def test_step_output_records_decision(
    release_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    allowed: bool,
) -> None:
    module, state = release_context
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(state["event"]), encoding="utf-8")
    output_path = tmp_path / "output"
    for name, value in {
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": SHA,
        "GITHUB_OUTPUT": str(output_path),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "ready", lambda *args, **kwargs: allowed)
    assert cli.main(["check-release-readiness"]) == 0
    assert output_path.read_text() == f"ready={str(allowed).lower()}\n"

    def fail(*args: object) -> None:
        raise RuntimeError("API unavailable")

    output_path.unlink()
    monkeypatch.setattr(module, "ready", fail)
    assert cli.main(["check-release-readiness"]) == 1
    assert not output_path.exists()


def test_initialization_never_authorizes_release(
    release_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = release_context
    state["jobs"][0]["conclusion"] = "skipped"
    assert not module.ready(
        "workflow_run", state["event"], REPOSITORY, "refs/heads/main", SHA, root=Path.cwd()
    )
    with pytest.raises(ValueError, match="Merged PR verification"):
        module.ready("workflow_dispatch", {}, REPOSITORY, "refs/heads/main", SHA, root=Path.cwd())


def recover(module: ModuleType, state: dict[str, Any]) -> bool:
    return module.ready(
        "workflow_dispatch",
        state["event"],
        REPOSITORY,
        "refs/heads/main",
        state["merge"],
        root=Path.cwd(),
    )


def test_fresh_main_ci_recovers_without_original_pr_artifact(
    recovery_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = recovery_context
    assert recover(module, state)


def test_recovery_checks_preserved_commit_subjects(
    recovery_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = recovery_context
    git = state["git"]
    head = git("commit-tree", state["tree"], "-p", state["head"], "-m", "Unconventional")
    merged = git("commit-tree", state["tree"], "-p", state["base"], "-p", head, "-m", "fix: merge")
    state.update(merge=merged, current=merged)
    state["pr"].update(merge_commit_sha=merged)
    state["pr"]["head"]["sha"] = head
    state["runs"][0]["head_sha"] = merged
    state["evidence"].update(head_sha=merged, checkout_sha=merged)
    with pytest.raises(ValueError, match="merged PR commit subject"):
        recover(module, state)


@pytest.mark.parametrize("defect", ["missing", "skipped", "failure", "duplicate"])
def test_recovery_requires_all_quality_jobs(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    defect: str,
) -> None:
    module, state = recovery_context
    if defect == "missing":
        state["jobs"].pop()
    elif defect == "duplicate":
        state["jobs"].append(deepcopy(state["jobs"][0]))
    else:
        state["jobs"][0]["conclusion"] = defect
    with pytest.raises(ValueError, match="required CI job"):
        recover(module, state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("workflow_id", 99),
        ("event", "pull_request"),
        ("head_branch", "topic"),
        ("head_sha", "wrong"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("repository", {"full_name": "other/repo"}),
        ("head_repository", {"full_name": "fork/repo"}),
    ],
)
def test_recovery_rejects_wrong_or_unfinished_run(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    field: str,
    value: object,
) -> None:
    module, state = recovery_context
    state["runs"][0][field] = value
    with pytest.raises(ValueError, match=field):
        recover(module, state)


@pytest.mark.parametrize("field", ["repository", "run_id", "head_sha", "checkout_sha", "tree_sha"])
def test_recovery_requires_matching_record(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    field: str,
) -> None:
    module, state = recovery_context
    state["evidence"][field] = "wrong"
    with pytest.raises(ValueError, match=field):
        recover(module, state)


def test_recovery_rejects_expired_evidence(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, state = recovery_context

    def expired(*args: object) -> None:
        raise RuntimeError("artifact expired")

    monkeypatch.setattr(github_checks, "validation_record", expired)
    with pytest.raises(RuntimeError, match="expired"):
        recover(module, state)


@pytest.mark.parametrize("race", ["newer", "rerun", "main"])
def test_recovery_cannot_authorize_stale_evidence(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    race: str,
) -> None:
    module, state = recovery_context

    def record(*args: object) -> dict[str, Any]:
        if race == "main":
            state["current"] = "b" * 40
        elif race == "rerun":
            state["runs"][0].update(status="in_progress", conclusion=None)
        else:
            newer = deepcopy(state["runs"][0])
            newer.update(id=101, conclusion="failure")
            state["runs"].append(newer)
        return state["evidence"]

    monkeypatch.setattr(github_checks, "validation_record", record)
    with pytest.raises(ValueError):
        recover(module, state)


def test_recovery_rejects_older_run_and_non_pr_commits(
    recovery_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = recovery_context
    state["event"]["inputs"]["recovery-run-id"] = "99"
    with pytest.raises(ValueError, match="latest manual"):
        recover(module, state)
    state["event"]["inputs"]["recovery-run-id"] = "100"
    state["candidates"] = []
    with pytest.raises(ValueError, match="merged PR"):
        recover(module, state)


@pytest.mark.parametrize("value", ["-1", "0", "one", "1.0", True, False, 0, None])
def test_recovery_input_validation(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    value: object,
) -> None:
    module, state = recovery_context
    state["event"]["inputs"]["recovery-run-id"] = value
    with pytest.raises(ValueError, match="positive run ID"):
        recover(module, state)


def test_bootstrap_root_cannot_use_recovery(
    recovery_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = recovery_context
    state["merge"] = state["base"]
    state["current"] = state["base"]
    state["runs"][0]["head_sha"] = state["base"]
    with pytest.raises(ValueError, match="one-parent commit or two-parent merge commit"):
        recover(module, state)


def test_recovery_requires_manual_release_on_main(
    recovery_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = recovery_context
    with pytest.raises(ValueError, match="main branch"):
        module.ready(
            "workflow_dispatch",
            state["event"],
            REPOSITORY,
            "refs/heads/topic",
            state["merge"],
            root=Path.cwd(),
        )
    with pytest.raises(ValueError, match="manual Release"):
        module.ready(
            "workflow_run",
            state["event"],
            REPOSITORY,
            "refs/heads/main",
            state["merge"],
            root=Path.cwd(),
        )
