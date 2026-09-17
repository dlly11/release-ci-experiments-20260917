"""Rebased PRs retain individual subjects but reuse CI only for their final tree."""

from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from repo_tools import cli

REPOSITORY = "owner/project"
pytestmark = pytest.mark.parametrize("merge_context", ["rebase"], indirect=True)


def test_rewritten_shas_and_different_intermediate_tree_reuse_one_pr_run(
    merge_context: tuple[ModuleType, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    module, state = merge_context
    git = state["git"]
    first, final = state["integration"]
    assert first != git("rev-parse", f"{state['head']}^")
    assert final != state["head"]
    assert git("show", "-s", "--format=%B", final) == git(
        "show", "-s", "--format=%B", state["head"]
    )
    assert git("rev-parse", f"{first}^{{tree}}") != state["tree"]
    assert module.verify_commit(REPOSITORY, final, 42) == [first, final]
    capsys.readouterr()
    assert cli.main(state["arguments"]) == 0
    assert capsys.readouterr().out.count("tested tree") == 1


def test_single_commit_rebase(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _module, state = merge_context
    git = state["git"]
    original = git("commit-tree", state["tree"], "-p", state["base"], "-m", "feat: one commit")
    with monkeypatch.context() as replay:
        replay.setenv("GIT_COMMITTER_DATE", "2001-01-01T00:00:00Z")
        final = git("commit-tree", state["tree"], "-p", state["base"], "-m", "feat: one commit")
    state.update(head=original, merge=final, integration=[final])
    state["pr"].update(merge_commit_sha=final)
    state["pr"]["head"]["sha"] = original
    state["runs"][0]["head_sha"] = original
    state["evidence"]["head_sha"] = original
    assert original != final
    assert cli.main(["check-merge", "--base", state["base"], "--head", final]) == 0


@pytest.mark.parametrize("boundary", ["start", "end"])
def test_push_cannot_split_a_rebased_pr(
    merge_context: tuple[ModuleType, dict[str, Any]],
    boundary: str,
) -> None:
    _module, state = merge_context
    base = state["integration"][0] if boundary == "start" else state["base"]
    head = state["integration"][0] if boundary == "end" else state["merge"]
    assert cli.main(["check-merge", "--base", base, "--head", head]) == 1


@pytest.mark.parametrize("defect", ["missing", "ambiguous", "wrong_tip", "unmerged", "wrong_base"])
def test_incomplete_or_ambiguous_rebased_pr_associations_fail_closed(
    merge_context: tuple[ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
) -> None:
    module, state = merge_context
    original = module.items
    candidates: list[dict[str, Any]] = [deepcopy(state["pr"])]
    if defect == "missing":
        candidates = []
    elif defect == "ambiguous":
        candidates.append(dict(state["pr"], number=2))
    elif defect == "wrong_tip":
        candidates[0]["merge_commit_sha"] = state["head"]
    elif defect == "unmerged":
        candidates[0]["merged_at"] = None
    else:
        candidates[0]["base"]["ref"] = "other"

    def items(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
        if f"/commits/{state['integration'][0]}/" in endpoint:
            return candidates
        return original(endpoint, key)

    monkeypatch.setattr(module, "items", items)
    assert cli.main(state["arguments"]) == 1


@pytest.mark.parametrize("defect", ["subject", "parents"])
def test_recovery_validates_intermediate_rebased_commits(
    recovery_context: tuple[ModuleType, dict[str, Any]],
    defect: str,
) -> None:
    module, state = recovery_context
    git = state["git"]
    extra_parents = ["-p", state["head"]] if defect == "parents" else []
    subject = "fix: first change" if defect == "parents" else "fixup! first change"
    first = git("commit-tree", state["tree"], "-p", state["base"], *extra_parents, "-m", subject)
    final = git("commit-tree", state["tree"], "-p", first, "-m", "feat: final change")
    state.update(merge=final, current=final, integration=[first, final])
    state["pr"]["merge_commit_sha"] = final
    state["runs"][0]["head_sha"] = final
    state["evidence"].update(head_sha=final, checkout_sha=final)
    with pytest.raises(ValueError, match="rebased PR commit"):
        module.ready(
            "workflow_dispatch",
            state["event"],
            REPOSITORY,
            "refs/heads/main",
            final,
            root=Path.cwd(),
        )


def test_direct_commit_after_rebased_pr_is_rejected(
    merge_context: tuple[ModuleType, dict[str, Any]],
) -> None:
    _module, state = merge_context
    direct = state["git"](
        "commit-tree", state["tree"], "-p", state["merge"], "-m", "fix: direct push"
    )
    assert cli.main(["check-merge", "--base", state["base"], "--head", direct]) == 1
