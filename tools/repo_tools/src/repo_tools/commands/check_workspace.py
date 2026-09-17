"""Check Python component registrations against the actual uv workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repo_tools.python_smoke_checks import SMOKE_CHECKS
from repo_tools.repository_metadata import (
    discover_members,
    normalized_name,
    read_project,
    registration_errors,
)

RELEASE_CONFIG = Path("tools/release-please/config.json")


def workspace_errors(root: Path) -> list[str]:
    """Validate existing registries without adding a new component manifest."""
    config = read_project(root / "pyproject.toml")
    members, errors = discover_members(root, config)
    names = [member.name for member in members]
    root_name = normalized_name(config["project"]["name"])
    all_names = [root_name, *names]
    namespaces = [namespace for member in members for namespace in sorted(member.namespaces)]
    errors.extend(registration_errors("workspace distribution names", all_names, all_names))
    errors.extend(registration_errors("workspace import namespaces", namespaces, namespaces))

    expected_projects = {
        Path("pyproject.toml"): root_name,
        **{member.path / "pyproject.toml": member.name for member in members},
    }
    smoke_names = [normalized_name(name) for name in SMOKE_CHECKS]
    errors.extend(registration_errors("python_smoke_checks.SMOKE_CHECKS", names, smoke_names))
    member_namespaces = {member.name: member.namespaces for member in members}
    for name, smoke in SMOKE_CHECKS.items():
        namespace = smoke.namespace
        if (
            normalized_name(name) in member_namespaces
            and namespace not in member_namespaces[normalized_name(name)]
        ):
            errors.append(
                f"SMOKE_CHECKS[{name!r}]: namespace {namespace!r} "
                "is missing from that member's src directory"
            )

    errors.extend(
        registration_errors(
            "pyproject.toml: tool.coverage.run.source",
            namespaces,
            config["tool"]["coverage"]["run"]["source"],
        )
    )
    errors.extend(
        registration_errors(
            "pyproject.toml: tool.ruff.lint.isort.known-first-party",
            [*namespaces, "repo_tools"],
            config["tool"]["ruff"]["lint"]["isort"]["known-first-party"],
        )
    )

    try:
        release = json.loads((root / RELEASE_CONFIG).read_text(encoding="utf-8"))
        extra_files = release["packages"]["."]["extra-files"]
        # Other entries, including the native CMake version, retain their own checks.
        entries = [
            entry if isinstance(entry, dict) else {"path": entry}
            for entry in extra_files
            if (isinstance(entry, dict) and str(entry.get("path", "")).endswith("pyproject.toml"))
            or (isinstance(entry, str) and entry.endswith("pyproject.toml"))
        ]
        errors.extend(
            registration_errors(
                f"{RELEASE_CONFIG}: Python extra-files",
                (path.as_posix() for path in expected_projects),
                (entry["path"] for entry in entries),
            )
        )
        for entry in entries:
            if entry.get("type") != "toml" or entry.get("jsonpath") != "$.project.version":
                errors.append(
                    f"{RELEASE_CONFIG}: {entry['path']} requires type='toml' "
                    "and jsonpath='$.project.version'"
                )
    except (OSError, KeyError, TypeError, ValueError) as error:
        errors.append(f"{RELEASE_CONFIG}: {error}")
    return errors


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Report all registration discrepancies and return a failing status if needed."""
    try:
        errors = workspace_errors(root)
    except (OSError, KeyError, TypeError, ValueError) as error:
        errors = [f"invalid workspace configuration: {error}"]
    for error in errors:
        print(f"workspace check failed: {error}", file=sys.stderr)
    if errors:
        return 1
    print("all Python workspace components have consistent registrations")
    return 0
