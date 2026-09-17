"""Reuse PR checks only when the merged Git tree and complete CI evidence agree."""

import json
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from repo_tools import cli, github_checks

REPOSITORY = "owner/project"


def test_merge_sha_changes_but_tested_tree_matches(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    _module, state = merge_context
    assert state["head"] != state["merge"]
    assert cli.main(state["arguments"]) == 0


@pytest.mark.parametrize("second_method", ["squash", "merge", "rebase"])
def test_push_can_mix_merge_methods(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    second_method: str,
) -> None:
    module, state = merge_context
    git = state["git"]
    (tmp_path / "source.txt").write_text("second PR\n", encoding="utf-8")
    git("add", "source.txt")
    tree = git("write-tree")
    head = git("commit-tree", tree, "-p", state["merge"], "-m", "feat: second change")
    parents = ["-p", state["merge"]]
    if second_method == "merge":
        parents.extend(["-p", head])
    merged = git("commit-tree", tree, *parents, "-m", "feat: second change (#2)")
    integration = [merged]
    if second_method == "rebase":
        head = git("commit-tree", tree, "-p", head, "-m", "docs: explain second change")
        final = git("commit-tree", tree, "-p", merged, "-m", "docs: explain second change")
        integration.append(final)
        merged = final
    pr = deepcopy(state["pr"])
    pr.update(number=2, merge_commit_sha=merged)
    pr["head"].update(sha=head, ref="second-topic")
    run = dict(state["runs"][0], id=200, head_sha=head, head_branch="second-topic")
    evidence = dict(state["evidence"], run_id=200, head_sha=head, tree_sha=tree)
    original_api, original_items = module.api, module.items

    def api(endpoint: str) -> dict[str, Any]:
        if endpoint.endswith("/pulls/2"):
            return pr
        if endpoint.endswith("/runs/200"):
            return run
        return original_api(endpoint)

    def items(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
        if any(f"/commits/{sha}/pulls?" in endpoint for sha in integration):
            return [pr]
        if f"head_sha={head}" in endpoint:
            return [run]
        return original_items(endpoint, key)

    monkeypatch.setattr(module, "api", api)
    monkeypatch.setattr(module, "items", items)
    monkeypatch.setattr(
        module,
        "validation_record",
        lambda repository, run_id: evidence if run_id == 200 else state["evidence"],
    )
    assert cli.main(["check-merge", "--base", state["base"], "--head", merged]) == 0
    output = capsys.readouterr().out
    assert "PR #1's tested tree" in output and "PR #2's tested tree" in output


def test_preserved_commit_subjects_are_checked(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = merge_context
    git = state["git"]
    head = git("commit-tree", state["tree"], "-p", state["head"], "-m", "fixup! change")
    commit = git("commit-tree", state["tree"], "-p", state["base"], "-p", head, "-m", "fix: merge")
    state["pr"].update(merge_commit_sha=commit)
    state["pr"]["head"]["sha"] = head
    with pytest.raises(ValueError, match="merged PR commit subject"):
        module.verify_commit(REPOSITORY, commit, 42)


def test_manual_release_branch_ci_and_fork_pr_ci(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    _module, state = merge_context
    state["runs"][0]["event"] = "workflow_dispatch"
    assert cli.main(state["arguments"]) == 0
    state["pr"]["head"]["repo"]["full_name"] = "fork/project"
    assert cli.main(state["arguments"]) == 1
    state["runs"][0]["event"] = "pull_request"
    assert cli.main(state["arguments"]) == 0


@pytest.mark.parametrize("key", ["tree_sha", "head_sha", "run_id", "repository", "schema"])
def test_mismatched_validation_record_is_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]], key: str
) -> None:
    _module, state = merge_context
    state["evidence"][key] = "wrong"
    assert cli.main(state["arguments"]) == 1


@pytest.mark.parametrize("change", ["missing", "skipped", "failed", "duplicate"])
def test_every_required_ci_job_must_actually_pass(
    merge_context: tuple[ModuleType, dict[str, Any]], change: str
) -> None:
    _module, state = merge_context
    if change == "missing":
        state["jobs"].pop()
    elif change == "duplicate":
        state["jobs"].append(deepcopy(state["jobs"][0]))
    else:
        state["jobs"][0]["conclusion"] = change
    assert cli.main(state["arguments"]) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_id", 99),
        ("path", "other.yml"),
        ("head_sha", "wrong"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("event", "push"),
        ("head_branch", "other"),
        ("repository", {"full_name": "other/project"}),
    ],
)
def test_wrong_or_unsuccessful_ci_run_is_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]], field: str, value: object
) -> None:
    _module, state = merge_context
    state["runs"][0][field] = value
    assert cli.main(state["arguments"]) == 1


def test_new_failed_run_cannot_reuse_old_success(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    _module, state = merge_context
    newer = deepcopy(state["runs"][0])
    newer.update(id=101, conclusion="failure")
    state["runs"].append(newer)
    assert cli.main(state["arguments"]) == 1


def test_missing_or_ambiguous_pr_is_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    _module, state = merge_context
    state["candidates"] = []
    assert cli.main(state["arguments"]) == 1
    state["candidates"] = [state["pr"], state["pr"]]
    assert cli.main(state["arguments"]) == 1


def test_missing_artifact_and_api_errors_fail_closed(
    merge_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, state = merge_context

    def fail(*args: object) -> None:
        raise RuntimeError("artifact expired or unavailable")

    monkeypatch.setattr(module, "validation_record", fail)
    assert cli.main(state["arguments"]) == 1


def test_rerun_started_during_download_is_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module, state = merge_context

    def download(*args: object) -> dict[str, Any]:
        state["runs"][0]["status"] = "in_progress"
        return state["evidence"]

    monkeypatch.setattr(module, "validation_record", download)
    assert cli.main(state["arguments"]) == 1


def test_nonconventional_subject_and_unsupported_parent_counts_are_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = merge_context
    git = state["git"]
    invalid = git("commit-tree", state["tree"], "-p", state["base"], "-m", "Update things")
    with pytest.raises(ValueError, match="subject"):
        module.verify_commit(REPOSITORY, invalid, 42)
    for parents in [[], [state["base"], state["head"], invalid]]:
        args = [arg for parent in parents for arg in ("-p", parent)]
        commit = git("commit-tree", state["tree"], *args, "-m", "fix: merge")
        with pytest.raises(ValueError, match="two-parent merge commit"):
            module.verify_commit(REPOSITORY, commit, 42)


def test_merge_must_preserve_the_original_pr_head(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = merge_context
    git = state["git"]
    other = git("commit-tree", state["tree"], "-p", state["base"], "-m", "fix: unrelated")
    commit = git("commit-tree", state["tree"], "-p", state["base"], "-p", other, "-m", "fix: merge")
    state["pr"]["merge_commit_sha"] = commit
    with pytest.raises(ValueError, match="second parent"):
        module.verify_commit(REPOSITORY, commit, 42)


def test_default_github_merge_subject_is_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = merge_context
    commit = state["git"](
        "commit-tree",
        state["tree"],
        "-p",
        state["base"],
        "-p",
        state["head"],
        "-m",
        "Merge pull request #1 from owner/topic",
    )
    state["pr"]["merge_commit_sha"] = commit
    with pytest.raises(ValueError, match="subject"):
        module.verify_commit(REPOSITORY, commit, 42)


def test_record_uses_actual_synthetic_merge_tree(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module, state = merge_context
    git = state["git"]
    synthetic = git(
        "commit-tree",
        state["tree"],
        "-p",
        state["base"],
        "-p",
        state["head"],
        "-m",
        "Synthetic PR merge",
    )
    git("checkout", "--detach", synthetic)
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"head": {"sha": state["head"]}}}), encoding="utf-8"
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_SHA", synthetic)
    output = tmp_path / "validation.json"
    module.record(output)
    record = json.loads(output.read_text())
    assert record["tree_sha"] == state["tree"]
    assert record["checkout_sha"] == synthetic
    assert record["head_sha"] == state["head"]
    monkeypatch.setenv("GITHUB_SHA", state["head"])
    with pytest.raises(ValueError, match="checkout"):
        module.record(output)


def test_metadata_download_selects_exact_run_and_reads_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = github_checks

    def gh(*args: str) -> str:
        assert args[:6] == ("run", "download", "123", "--repo", REPOSITORY, "--name")
        (Path(args[-1]) / "validation.json").write_text('{"schema": 1}', encoding="utf-8")
        return ""

    monkeypatch.setattr(module, "gh", gh)
    assert module.validation_record(REPOSITORY, 123) == {"schema": 1}


@pytest.mark.parametrize("base", ["0" * 40, "0" * 64])
def test_initialization_has_actionable_diagnostic(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    base: str,
) -> None:
    _module, state = merge_context
    arguments = ["check-merge", "--base", base, "--head", state["merge"]]
    assert cli.main(arguments) == 1
    assert "initial branch creation has no merged PR" in capsys.readouterr().err


def test_recovery_record_requires_exact_checkout(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    module, state = merge_context
    state["evidence"]["head_sha"] = state["merge"]
    with pytest.raises(ValueError, match="checkout_sha"):
        module.check_evidence(REPOSITORY, 100, state["merge"], state["merge"], exact_checkout=True)
    state["evidence"]["checkout_sha"] = state["merge"]
    module.check_evidence(REPOSITORY, 100, state["merge"], state["merge"], exact_checkout=True)


@pytest.mark.parametrize("conclusion", ["success", "failure", None])
def test_new_run_during_download_invalidates_selected_evidence(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    conclusion: str | None,
) -> None:
    module, state = merge_context

    def download(*args: object) -> dict[str, Any]:
        newer = deepcopy(state["runs"][0])
        newer.update(id=101, conclusion=conclusion)
        state["runs"].append(newer)
        return state["evidence"]

    monkeypatch.setattr(module, "validation_record", download)
    with pytest.raises(ValueError, match="newer PR CI run"):
        module.verify_commit(REPOSITORY, state["merge"], 42)


def test_missing_merged_evidence_explains_current_recovery(merge_context, monkeypatch, capsys):
    module, state = merge_context

    def missing(*args):
        raise ValueError("validation artifact unavailable")

    monkeypatch.setattr(module, "validation_record", missing)
    assert cli.main(state["arguments"]) == 1
    message = capsys.readouterr().err
    assert "current main" in message and "recovery-run-id" in message
    assert "Historical schema-1" in message
    assert "retry PR CI within 30 days" not in message
