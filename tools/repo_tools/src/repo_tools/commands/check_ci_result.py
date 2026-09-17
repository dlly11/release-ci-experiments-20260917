"""Require the selected CI jobs or authoritative dispatch evidence before passing the gate."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from repo_tools.ci_validation import finish, write_summary


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--record", type=Path, default=Path("build/pr-validation/validation.json"))


def execute(args: argparse.Namespace, *, root: Path) -> int:
    selected = None
    try:
        selected = json.loads(os.environ["CI_CONTEXT"])
        result = finish(root, selected, args.record)
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        write_summary("CI result", selected, error=str(error))
        print(f"CI validation failed: {error}", file=sys.stderr)
        return 1
    write_summary("CI result", selected, result=result)
    return 0
