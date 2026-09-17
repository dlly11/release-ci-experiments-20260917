"""Read repository components, versions, and Git metadata without changing them."""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def normalized_name(name: str) -> str:
    """Normalize a distribution name for comparisons with wheel metadata."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Member:
    """A discovered member, with paths relative to the repository root."""

    path: Path
    name: str
    namespaces: frozenset[str]


def read_project(path: Path) -> dict[str, Any]:
    """Read TOML with the source path included in parse and I/O errors."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from error


def discover_members(root: Path, config: dict[str, Any]) -> tuple[list[Member], list[str]]:
    """Expand member/exclude globs and discover the template's src-layout packages."""
    workspace = config
    field = ""
    for key in ("tool", "uv", "workspace"):
        field = f"{field}.{key}" if field else key
        value = workspace.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"{root / 'pyproject.toml'}: {field} must be a table")
        workspace = value

    def expand(key: str, default: Any = None) -> set[Path]:
        patterns = workspace.get(key, default)
        label = f"{root / 'pyproject.toml'}: tool.uv.workspace.{key}"
        if not isinstance(patterns, list) or any(
            not isinstance(pattern, str) or not pattern for pattern in patterns
        ):
            raise ValueError(f"{label} must be a list of nonempty strings")
        paths = set()
        for pattern in patterns:
            try:
                paths.update(path.resolve() for path in root.glob(pattern))
            except (ValueError, NotImplementedError) as error:
                raise ValueError(f"{label}: invalid glob {pattern!r}: {error}") from error
        return paths

    paths = expand("members") - expand("exclude", [])
    members: list[Member] = []
    errors: list[str] = []
    for path in sorted(paths):
        if path == root or not path.is_relative_to(root):
            errors.append(f"workspace members: expected a component below the root, found {path}")
            continue
        relative = path.relative_to(root)
        try:
            name = read_project(path / "pyproject.toml")["project"]["name"]
            if not isinstance(name, str) or not name.strip():
                raise ValueError("project.name must be a non-empty string")
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"{relative}/pyproject.toml: {error}")
            continue
        namespaces = frozenset(
            package.parent.name for package in (path / "src").glob("*/__init__.py")
        )
        if not namespaces:
            errors.append(f"{relative}: no import package found at src/<namespace>/__init__.py")
        members.append(Member(relative, normalized_name(name), namespaces))
    return members, errors


def registration_errors(label: str, expected: Iterable[str], actual: Iterable[str]) -> list[str]:
    """Describe missing, stale, and duplicate entries in a registration list."""
    expected_set = set(expected)
    counts = Counter(actual)
    errors = [f"{label}: missing {value}" for value in sorted(expected_set - counts.keys())]
    errors.extend(f"{label}: stale {value}" for value in sorted(counts.keys() - expected_set))
    errors.extend(
        f"{label}: duplicate {value}" for value, count in sorted(counts.items()) if count > 1
    )
    return errors


def python_projects(root: Path) -> dict[Path, str]:
    """Discover every version-bearing Python project, rejecting ambiguous workspaces."""
    config = read_project(root / "pyproject.toml")
    members, errors = discover_members(root, config)
    projects = {Path("pyproject.toml"): normalized_name(config["project"]["name"])}
    projects.update({member.path / "pyproject.toml": member.name for member in members})
    names = list(projects.values())
    namespaces = [namespace for member in members for namespace in member.namespaces]
    errors.extend(registration_errors("workspace distribution names", names, names))
    errors.extend(registration_errors("workspace import namespaces", namespaces, namespaces))
    if errors:
        raise ValueError("; ".join(errors))
    return projects


def repository_version(root: Path) -> str:
    """Return the canonical repository version."""
    version = (root / "version.txt").read_text(encoding="utf-8").strip()
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"version.txt must contain X.Y.Z, found {version!r}")
    return version


def project_metadata(root: Path, path: Path) -> tuple[str, str]:
    """Return a project's distribution name and version."""
    with (root / path).open("rb") as file:
        project = tomllib.load(file)["project"]
    return normalized_name(project["name"]), str(project["version"])


@dataclass(frozen=True)
class _CMakeToken:
    """An argument or delimiter with offsets into the unchanged source text."""

    value: str
    start: int
    end: int
    kind: str


def _cmake_tokens(contents: str) -> list[_CMakeToken]:
    """Skip comments and preserve quoted arguments without evaluating CMake code."""
    pattern = re.compile(
        r"(?P<space>\s+)|(?P<bracket>#?\[=*\[)|(?P<comment>\#[^\r\n]*)"
        r'|(?P<quoted>"(?:\\[\s\S]|[^"\\])*")|(?P<paren>[()])'
        r'|(?P<word>(?:\\[\s\S]|"(?:\\[\s\S]|[^"\\])*"|[^\s()#"\\])+)'
    )
    tokens = []
    position = 0
    while position < len(contents):
        match = pattern.match(contents, position)
        if match is None:
            raise ValueError("CMakeLists.txt: unsupported or unterminated argument")
        kind = str(match.lastgroup)
        start, end = match.span()
        position = end
        if kind in {"space", "comment"}:
            continue
        if kind == "bracket":
            opening = match.group().lstrip("#")
            closing = "]" + "=" * (len(opening) - 2) + "]"
            end = contents.find(closing, position)
            if end < 0:
                raise ValueError("CMakeLists.txt: unterminated bracket argument or comment")
            position = end + len(closing)
            if match.group().startswith("#"):
                continue
            start = match.end()
            # CMake discards a newline immediately following a bracket opening.
            if contents.startswith("\r\n", start):
                start += 2
            elif contents.startswith("\n", start):
                start += 1
        elif kind == "quoted":
            start += 1
            end -= 1
        tokens.append(_CMakeToken(contents[start:end], start, end, kind))
    return tokens


def cmake_project_version(contents: str) -> tuple[str, int, int]:
    """Locate one literal project VERSION and its span; reject ambiguous declarations."""
    tokens = _cmake_tokens(contents)
    projects = []
    depth = 0
    project_start = None
    for index, token in enumerate(tokens):
        if token.kind != "paren":
            continue
        if token.value == "(":
            if depth == 0 and index > 0:
                command = tokens[index - 1]
                if command.kind == "word" and command.value.lower() == "project":
                    project_start = index + 1
            depth += 1
        else:
            depth -= 1
            if depth < 0:
                raise ValueError("CMakeLists.txt: unmatched closing parenthesis")
            if depth == 0 and project_start is not None:
                projects.append(tokens[project_start:index])
                project_start = None
    if depth or len(projects) != 1:
        raise ValueError("CMakeLists.txt: require exactly one complete project(...) declaration")
    arguments = projects[0]
    versions = [index for index, token in enumerate(arguments[1:], 1) if token.value == "VERSION"]
    if (
        len(versions) != 1
        or versions[0] + 1 >= len(arguments)
        or any(token.kind == "paren" for token in arguments)
    ):
        raise ValueError("CMakeLists.txt: project(...) must declare exactly one literal VERSION")
    version = arguments[versions[0] + 1]
    if VERSION_PATTERN.fullmatch(version.value) is None:
        raise ValueError("CMakeLists.txt: project VERSION must be literal X.Y.Z, not an expression")
    return version.value, version.start, version.end


def cmake_version(root: Path) -> str:
    """Return the version declared by the root CMake project."""
    contents = (root / "CMakeLists.txt").read_text(encoding="utf-8")
    return cmake_project_version(contents)[0]


def locked_versions(root: Path) -> dict[str, str]:
    """Return versions for repository projects recorded in uv.lock."""
    with (root / "uv.lock").open("rb") as file:
        packages = tomllib.load(file)["package"]
    expected_names = set(python_projects(root).values())
    return {
        str(package["name"]): str(package["version"])
        for package in packages
        if package["name"] in expected_names
    }


def version_errors(root: Path, expected: str, expected_tag: str | None = None) -> list[str]:
    """Describe all metadata that differs from the expected version."""
    errors: list[str] = []

    projects = python_projects(root)
    for path in projects:
        _, version = project_metadata(root, path)
        if version != expected:
            errors.append(f"{path}: expected version {expected}, found {version}")

    native_version = cmake_version(root)
    if native_version != expected:
        errors.append(f"CMakeLists.txt: expected version {expected}, found {native_version}")

    locked = locked_versions(root)
    for name in projects.values():
        version = locked.get(name)
        if version is None:
            errors.append(f"uv.lock: missing workspace project {name}")
        elif version != expected:
            errors.append(f"uv.lock: {name} expected version {expected}, found {version}")

    if expected_tag is not None and expected_tag != f"v{expected}":
        errors.append(f"release tag: expected v{expected}, found {expected_tag}")

    return errors


def git(*arguments: str, root: Path | None = None) -> str:
    """Read Git metadata without shell interpretation or signature output."""
    return subprocess.run(
        ["git", "-c", "log.showSignature=false", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout
