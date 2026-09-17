"""Validate optional release credentials and the exact PR eligible for auto-merge."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from repo_tools.conventional_commits import valid_subject
from repo_tools.github_api import api, repository_name
from repo_tools.release_changes import CONFIG, branch_at, release_branch


def configuration(environment: Mapping[str, str]) -> tuple[str, bool]:
    """Choose credentials explicitly; never substitute another identity on failure."""
    mode = environment.get("RELEASE_AUTH_MODE", "") or "github-token"
    setting = environment.get("RELEASE_AUTO_MERGE", "") or "false"
    if mode not in {"github-token", "app", "pat"}:
        raise ValueError("RELEASE_AUTH_MODE must be github-token, app, or pat")
    if setting not in {"true", "false"}:
        raise ValueError("RELEASE_AUTO_MERGE must be true or false")
    required = {
        "github-token": (),
        "app": ("RELEASE_APP_CLIENT_ID", "RELEASE_APP_PRIVATE_KEY"),
        "pat": ("RELEASE_PAT",),
    }[mode]
    for name in required:
        if not environment.get(name, "").strip():
            raise ValueError(f"{name} is required for {mode} release authentication")
    automatic = setting == "true"
    if automatic and mode == "github-token":
        raise ValueError("release auto-merge requires app or pat authentication for post-merge CI")
    return mode, automatic


def eligible_pr(
    repository: str, number: int, branch: str, head: str, *, root: Path, revision: str | None = None
) -> str:
    """Bind auto-merge to Release Please's managed branch and synchronized commit."""
    expected = (
        branch_at(root, revision)
        if revision
        else release_branch(json.loads((root / CONFIG).read_text()))
    )
    if number < 1 or branch != expected or not head:
        raise ValueError("expected a positive release PR number, managed main branch, and head SHA")
    pr = api(f"repos/{repository}/pulls/{number}")
    if pr["state"] != "open" or pr["draft"]:
        raise ValueError("release PR must be open and ready for review")
    for side in ("base", "head"):
        if (pr[side]["repo"] or {}).get("full_name") != repository:
            raise ValueError("release PR must use this repository for both base and head")
    if pr["base"]["ref"] != "main" or pr["head"]["ref"] != branch or pr["head"]["sha"] != head:
        raise ValueError("release PR branch or head changed before auto-merge")
    if "autorelease: pending" not in {label["name"] for label in pr["labels"]}:
        raise ValueError("release PR must have Release Please's pending label")
    title = pr["title"]
    if not valid_subject(title) or not title.startswith("chore(main): release "):
        raise ValueError("release PR title must be a conventional main release title")
    return title


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pr", type=int, help="validate the PR returned by Release Please")
    parser.add_argument("--branch")
    parser.add_argument("--expected-head")


def execute(args: argparse.Namespace, *, root: Path) -> int:
    try:
        if args.pr is None:
            if args.branch is not None or args.expected_head is not None:
                raise ValueError("--branch and --expected-head require --pr")
            mode, automatic = configuration(os.environ)
            if automatic:
                repository = repository_name(os.environ.get("GITHUB_REPOSITORY"), root=root)
                if api(f"repos/{repository}")["allow_auto_merge"] is not True:
                    raise ValueError("enable repository Allow auto-merge before RELEASE_AUTO_MERGE")
            outputs = {"auth-mode": mode, "auto-merge": str(automatic).lower()}
            print(f"Release authentication: {mode}; auto-merge: {automatic}")
        else:
            repository = repository_name(os.environ.get("GITHUB_REPOSITORY"), root=root)
            title = eligible_pr(repository, args.pr, args.branch, args.expected_head, root=root)
            outputs = {"title": title}
            print(f"Release PR #{args.pr} is eligible at {args.expected_head}.")
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a", encoding="utf-8") as stream:
                for name, value in outputs.items():
                    stream.write(f"{name}={value}\n")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"release automation validation failed: {error}", file=sys.stderr)
        return 1
    return 0
