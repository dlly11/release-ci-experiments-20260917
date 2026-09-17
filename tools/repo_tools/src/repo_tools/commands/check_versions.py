"""Check that every release-bearing component uses the repository version."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_tools.repository_metadata import repository_version, version_errors


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    parser.add_argument("--tag", help="also require this release tag to equal v<version>")


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Run the version consistency check."""

    try:
        expected = repository_version(root)
        errors = version_errors(root, expected, args.tag)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"version check failed: {error}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"version check failed: {error}", file=sys.stderr)
        return 1

    print(f"all repository components use version {expected}")
    return 0
