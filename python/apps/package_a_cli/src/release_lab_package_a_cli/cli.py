"""Command-line interface for Python Package A."""

import argparse
from collections.abc import Sequence

from release_lab_package_a import GreetingService


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Create a Package A greeting.")
    parser.add_argument("name", help="person or system to greet")
    parser.add_argument("--prefix", default="Hello", help="greeting prefix")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        message = GreetingService(prefix=args.prefix).greet(args.name)
    except ValueError as error:
        parser.error(str(error))
    print(message.text)
    return 0
