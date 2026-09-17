"""Incomplete Git history must never authorize a PR integration or its recovery."""

from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock

import pytest


def test_shallow_history_is_rejected_before_github_reads(
    merge_context: tuple[ModuleType, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, state = merge_context
    shallow = tmp_path / "shallow clone"
    state["git"]("clone", "--depth", "2", tmp_path.as_uri(), str(shallow))
    assert (
        module.merged_pr("owner/project", state["merge"], root=tmp_path)[1] == state["integration"]
    )
    api = Mock(side_effect=AssertionError("must reject shallow history before GitHub reads"))
    monkeypatch.setattr(module, "api", api)
    monkeypatch.setattr(module, "items", api)
    with pytest.raises(ValueError, match="full Git history"):
        module.merged_pr("owner/project", state["merge"], root=shallow)
    api.assert_not_called()


@pytest.mark.parametrize("merge_context", ["merge"], indirect=True)
def test_earlier_invalid_merge_subject_cannot_hide_behind_shallow_boundary(
    merge_context: tuple[ModuleType, dict[str, Any]], tmp_path: Path
) -> None:
    module, state = merge_context
    git = state["git"]
    first = git("commit-tree", state["tree"], "-p", state["base"], "-m", "Invalid earlier subject")
    head = git("commit-tree", state["tree"], "-p", first, "-m", "fix: final PR change")
    merge = git(
        "commit-tree", state["tree"], "-p", state["base"], "-p", head, "-m", "fix: merge PR"
    )
    state["pr"].update(merge_commit_sha=merge)
    state["pr"]["head"]["sha"] = head
    git("update-ref", "refs/heads/main", merge)
    shallow = tmp_path / "shallow clone"
    git("clone", "--depth", "2", tmp_path.as_uri(), str(shallow))
    with pytest.raises(ValueError, match="subject is not conventional"):
        module.merged_pr("owner/project", merge, root=tmp_path)
    with pytest.raises(ValueError, match="full Git history"):
        module.merged_pr("owner/project", merge, root=shallow)
