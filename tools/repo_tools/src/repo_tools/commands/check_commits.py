"""Validate a commit-message file or every commit introduced by a Git revision range."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from repo_tools.conventional_commits import check_message
from repo_tools.repository_metadata import git


def commits_between(base: str, head: str, *, root: Path | None = None) -> list[str]:
    """Resolve refs first; an all-zero push base denotes a newly created branch."""
    head_sha = git(
        "rev-parse", "--verify", "--end-of-options", f"{head}^{{commit}}", root=root
    ).strip()
    if base in {"0" * 40, "0" * 64}:
        revision_range = head_sha
    else:
        base_sha = git(
            "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}", root=root
        ).strip()
        revision_range = f"{base_sha}..{head_sha}"
    return git("rev-list", "--reverse", revision_range, "--", root=root).splitlines()


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--message-file", type=Path, help="message file supplied by commit-msg")
    source.add_argument("--base", help="exclude commits reachable from this ref or SHA")
    parser.add_argument("--head", default="HEAD", help="last commit to check (default: HEAD)")


def execute(args: argparse.Namespace, *, root: Path | None = None) -> int:
    """Support the commit-msg hook and CI without additional dependencies."""
    try:
        if args.message_file is not None:
            return int(
                not check_message(
                    args.message_file.read_text(encoding="utf-8"), str(args.message_file)
                )
            )
        commits = commits_between(args.base, args.head, root=root)
        failures = 0
        for commit in commits:
            message = git("show", "--no-patch", "--format=%B", commit, "--", root=root)
            failures += not check_message(message, commit[:12])
        print(f"Checked {len(commits)} commit(s); {failures} invalid subject(s).")
        return int(failures != 0)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        print(f"cannot validate commits: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        return 1
