"""Select full, release-only, or delegated CI using committed inputs and live PR identity."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from repo_tools.ci_validation import context, write_summary
from repo_tools.release_changes import release_changes


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--classify", action="store_true", help="inspect Git changes locally without GitHub reads"
    )
    parser.add_argument("--base")
    parser.add_argument("--head")


def run(args: argparse.Namespace, *, root: Path) -> int:
    if args.classify:
        if not args.base or not args.head:
            raise ValueError("--classify requires --base and --head")
        valid, reason = release_changes(root, args.base, args.head)
        print(json.dumps({"release_only": valid, "reason": reason}))
        return 0
    if args.base or args.head:
        raise ValueError("--base and --head require --classify")
    selected = context(root)
    print(f"CI: {selected['role']} / {selected['profile']}: {selected['reason']}")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        for key in ("role", "profile"):
            stream.write(f"{key}={selected[key]}\n")
        stream.write("context=" + json.dumps(selected) + "\n")
    write_summary("CI context", selected)
    return 0


def execute(args: argparse.Namespace, *, root: Path) -> int:
    try:
        return run(args, root=root)
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        if not args.classify:
            write_summary("CI context", error=str(error))
        print(f"CI validation failed: {error}", file=sys.stderr)
        return 1
