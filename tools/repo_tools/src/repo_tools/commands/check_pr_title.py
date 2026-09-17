"""Validate a pull request title as a Conventional Commit subject."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from repo_tools.conventional_commits import valid_subject
from repo_tools.github_api import api, repository_name


def workflow_title(
    repository: str, number: int, expected_head: str, manual_branch: str | None
) -> str:
    """Validate the PR context before using its live title for a required check."""
    if number < 1:
        raise ValueError("PR number must be positive")
    pr = api(f"repos/{repository}/pulls/{number}")
    if pr["state"] != "open":
        raise ValueError(f"PR #{number} must be open, found {pr['state']!r}")
    if pr["base"]["repo"]["full_name"] != repository:
        raise ValueError(f"PR #{number} belongs to a different repository")
    if pr["head"]["sha"] != expected_head:
        raise ValueError(
            f"PR #{number} head: expected {expected_head!r}, found {pr['head']['sha']!r}"
        )
    if manual_branch is not None:
        expected_ref = f"refs/heads/{pr['head']['ref']}"
        if manual_branch != expected_ref:
            raise ValueError(
                f"PR #{number} branch: expected {expected_ref!r}, found {manual_branch!r}"
            )
        actual_repo = (pr["head"]["repo"] or {}).get("full_name")
        if actual_repo != repository:
            raise ValueError(
                f"PR #{number} head repository: expected {repository!r}, found {actual_repo!r}"
            )
    return pr["title"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    parser.add_argument("title", nargs="?")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--expected-head")


def execute(args: argparse.Namespace, *, root: Path | None = None) -> int:
    """Validate a standalone title, or a live PR tied to the workflow's head commit."""
    try:
        title = args.title
        if args.pr is not None:
            if title is not None or not args.expected_head:
                raise ValueError(
                    "--pr requires --expected-head and cannot be combined with a title"
                )
            event = os.environ.get("GITHUB_EVENT_NAME")
            if event not in {"pull_request", "workflow_dispatch"}:
                raise ValueError(
                    "live PR validation requires a pull_request or workflow_dispatch event"
                )
            title = workflow_title(
                repository_name(os.environ["GITHUB_REPOSITORY"]),
                args.pr,
                args.expected_head,
                os.environ["GITHUB_REF"] if event == "workflow_dispatch" else None,
            )
        elif args.expected_head is not None:
            raise ValueError("--expected-head requires --pr")
    except (KeyError, RuntimeError, TypeError, ValueError) as error:
        print(f"cannot validate PR title: {error}", file=sys.stderr)
        return 1
    if title is None or not valid_subject(title):
        print(f"invalid Conventional Commit pull request title: {title!r}", file=sys.stderr)
        print("example: feat(package-a): add JSON output", file=sys.stderr)
        return 1
    print(f"valid Conventional Commit pull request title: {title}")
    return 0
