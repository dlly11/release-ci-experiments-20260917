"""Check Python import locations before generating documentation or coverage output."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

from repo_tools.repository_metadata import discover_members, read_project

_IMPORT_LOCATIONS = """
import importlib.machinery
import importlib.util
import json
import sys

locations = {}
for name in json.loads(sys.argv[1]):
    parts = name.split('.')
    spec = importlib.util.find_spec(parts[0])
    for index in range(1, len(parts)):
        if spec is None or spec.submodule_search_locations is None:
            spec = None
            break
        # Looking up a dotted name with util.find_spec would import its parent.
        spec = importlib.machinery.PathFinder.find_spec(
            '.'.join(parts[:index + 1]), spec.submodule_search_locations
        )
    locations[name] = spec.origin if spec is not None else None
print(json.dumps(locations))
"""


def check_environment(root: Path, *, group: Literal["docs", "coverage"], command: str) -> None:
    """Require tools and editable first-party sources in the interpreter used by child tools."""
    members, errors = discover_members(root, read_project(root / "pyproject.toml"))
    if errors:
        raise ValueError("; ".join(errors))
    sources = {
        namespace: (root / member.path / "src" / namespace / "__init__.py").resolve()
        for member in members
        for namespace in sorted(member.namespaces)
    }
    if (root / "tools/repo_tools/pyproject.toml").is_file():
        sources["repo_tools"] = (root / "tools/repo_tools/src/repo_tools/__init__.py").resolve()
    modules = (
        ["sphinx", "breathe", "myst_parser", "sphinxcontrib.mermaid", "furo"]
        if group == "docs"
        else ["pytest", "pytest_cov", "gcovr"]
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _IMPORT_LOCATIONS, json.dumps([*sources, *modules])],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        locations = json.loads(result.stdout)
        for name, expected in sources.items():
            found = locations[name]
            if found is None or Path(found).resolve() != expected:
                errors.append(f"{name}: expected {expected}, found {found or 'not installed'}")
        errors.extend(f"missing Python module: {name}" for name in modules if not locations[name])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        errors.append(f"cannot inspect Python environment: {error}")
    if errors:
        raise ValueError(
            f"{command}: Python environment does not match the selected checkout:\n"
            + "\n".join(errors)
            + f"\nNo output directories were changed. From {root}, run:\n"
            f"  uv sync --locked --all-packages --group {group}\n"
            f"  uv run --no-sync repo-tools {command}"
        )
