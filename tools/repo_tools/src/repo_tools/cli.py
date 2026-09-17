"""One command-line interface for private repository maintenance."""

import argparse
import sys
from importlib import import_module
from pathlib import Path

from repo_tools.context import resolve_root

COMMANDS = (
    "build-docs",
    "check-ci-context",
    "check-ci-result",
    "check-commits",
    "check-coverage",
    "check-github-settings",
    "check-merge",
    "check-native-install",
    "check-pr-title",
    "check-python",
    "check-python-install",
    "check-release-automation",
    "check-release-readiness",
    "check-versions",
    "check-workspace",
    "doctor",
    "set-version",
)


def build_parser() -> argparse.ArgumentParser:
    """Create the full CLI without resolving a checkout or running commands."""
    parser = argparse.ArgumentParser(prog="repo-tools", description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, help="target checkout (default: discover from cwd)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        module = import_module(f"repo_tools.commands.{command.replace('-', '_')}")
        subparser = subparsers.add_parser(
            command,
            help=module.__doc__,
            description=module.__doc__,
        )
        module.add_arguments(subparser)
        subparser.set_defaults(execute=module.execute, parser=subparser)
    return parser


def main(argv: list[str] | None = None, *, default_root: Path | None = None) -> int:
    """Dispatch a parsed command with explicit context; help never needs a checkout."""
    args = build_parser().parse_args(argv)
    root = args.project_root if args.project_root is not None else default_root
    needs_root = args.command not in {"doctor", "check-pr-title"} and not (
        args.command == "check-commits" and args.message_file is not None
    )
    try:
        if root is not None or needs_root:
            root = resolve_root(root)
        return args.execute(args, root=root)
    except (OSError, ValueError) as error:
        print(f"repo-tools: {error}", file=sys.stderr)
        return 2 if args.command == "check-github-settings" else 1
