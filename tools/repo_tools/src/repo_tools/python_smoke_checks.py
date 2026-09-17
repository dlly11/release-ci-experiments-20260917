"""Explicit API and installed command checks for independently delivered Python wheels."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeCommand:
    """An executable in the wheel environment and its expected behavior."""

    executable: str
    arguments: tuple[str, ...]
    status: int = 0
    stdout: str | None = None
    stderr_contains: str | None = None


@dataclass(frozen=True)
class SmokeCheck:
    """One distribution's import namespace, API example, and optional CLI cases."""

    namespace: str
    example: str
    commands: tuple[SmokeCommand, ...] = ()


# Keep one observable API example per independently delivered component.
SMOKE_CHECKS = {
    "release-lab-core": SmokeCheck(
        "release_lab_core",
        """
from release_lab_core import (
    Message,
    MessageKind,
    create_message,
    normalize_name,
)
assert normalize_name(" Ada  Lovelace ") == "Ada Lovelace"
assert create_message(kind=MessageKind.GREETING, source="smoke", prefix="Hi", name="Ada") == (
    Message(kind=MessageKind.GREETING, source="smoke", text="Hi, Ada!")
)
""",
    ),
    "release-lab-package-a": SmokeCheck(
        "release_lab_package_a",
        """
from release_lab_package_a import GreetingService
message = GreetingService().greet("Ada")
assert (message.kind, message.source, message.text) == ("greeting", "package_a", "Hello, Ada!")
""",
    ),
    "release-lab-package-b": SmokeCheck(
        "release_lab_package_b",
        """
from release_lab_package_b import FarewellService
message = FarewellService().farewell("Ada")
assert (message.kind, message.source, message.text) == ("farewell", "package_b", "Goodbye, Ada!")
""",
    ),
    "release-lab-package-a-cli": SmokeCheck(
        "release_lab_package_a_cli",
        """
from release_lab_package_a_cli.cli import build_parser
assert build_parser().parse_args(["Ada"]).name == "Ada"
""",
        commands=(
            SmokeCommand("release-lab-package-a-cli", ("Ada",), stdout="Hello, Ada!\n"),
            SmokeCommand(
                "release-lab-package-a-cli",
                ("Ada", "--prefix", "Welcome"),
                stdout="Welcome, Ada!\n",
            ),
            SmokeCommand(
                "release-lab-package-a-cli",
                ("   ",),
                status=2,
                stdout="",
                stderr_contains="name must contain at least one non-whitespace character",
            ),
        ),
    ),
}

INSTALL_CHECK = """
import importlib
import importlib.metadata
import pathlib
import sys

name, namespace, expected_version = sys.argv[1:]
assert importlib.metadata.version(name) == expected_version
module = importlib.import_module(namespace)
location = pathlib.Path(module.__file__).resolve()
assert location.is_relative_to(pathlib.Path(sys.prefix).resolve()), location
assert location.with_name("py.typed").is_file(), "missing py.typed"
"""
