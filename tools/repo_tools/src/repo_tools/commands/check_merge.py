"""Record tested PR contents and verify GitHub squash, merge, or rebase integrations."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from repo_tools.github_api import api, repository_name
from repo_tools.github_checks import record, verify_commit
from repo_tools.repository_metadata import git


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--record", type=Path, help="write the PR validation record after quality checks"
    )
    mode.add_argument("--base", help="main commit before the push")
    parser.add_argument("--head", default="HEAD", help="main commit after the push")


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Record PR validation or account for every new main commit through tested PRs."""
    try:
        if args.record:
            record(args.record, root=root)
            return 0
        if args.base in {"0" * 40, "0" * 64}:
            raise ValueError(
                "initial branch creation has no merged PR to verify; run bootstrap quality "
                "checks and submit setup changes through a protected PR before releasing"
            )
        repository = repository_name(os.environ.get("GITHUB_REPOSITORY"), root=root)
        base = git(
            "rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}", root=root
        ).strip()
        head = git(
            "rev-parse", "--verify", "--end-of-options", f"{args.head}^{{commit}}", root=root
        ).strip()
        git("merge-base", "--is-ancestor", base, head, root=root)
        commits = git(
            "rev-list", "--reverse", "--first-parent", f"{base}..{head}", "--", root=root
        ).splitlines()
        if not commits:
            raise ValueError("push verification requires at least one new main commit")
        workflow_id = api(f"repos/{repository}/actions/workflows/ci.yml")["id"]
        while commits:
            integration = verify_commit(repository, commits[-1], workflow_id, root=root)
            if not integration or commits[-len(integration) :] != integration:
                raise ValueError(
                    "push boundary splits a PR integration or its commits are not contiguous"
                )
            del commits[-len(integration) :]
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"merge verification failed: {error}", file=sys.stderr)
        print(
            "For missing evidence after merging, run fresh full CI on current main and use "
            "Release recovery-run-id. Historical schema-1 retries are described in "
            "docs/releases.md#recovering-expired-ci-evidence.",
            file=sys.stderr,
        )
        return 1
    return 0
