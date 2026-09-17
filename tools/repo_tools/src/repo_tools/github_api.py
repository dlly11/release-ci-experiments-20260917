"""Small read-only GitHub CLI helpers for repository checks."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def gh(*arguments: str, root: Path | None = None) -> str:
    """Run a bounded GitHub CLI read and retain actionable error messages."""
    try:
        return subprocess.run(
            ["gh", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"GitHub read failed: {error.stderr.strip()}") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"cannot run GitHub CLI: {error}") from error


def api(endpoint: str) -> dict[str, Any]:
    """Read a JSON object; callers never issue API mutations."""
    result = json.loads(gh("api", "--method", "GET", endpoint))
    if not isinstance(result, dict):
        raise ValueError("GitHub API response must be a JSON object")
    return result


def repository_name(value: str | None = None, *, root: Path | None = None) -> str:
    """Resolve OWNER/REPO explicitly or from the current checkout."""
    name = (
        value
        if value is not None
        else gh(
            "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner", root=root
        ).strip()
    )
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) is None:
        raise ValueError(f"expected OWNER/REPO, found {name!r}")
    return name


def items(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
    """Read every page of an API collection, including endpoints returning arrays."""
    pages = json.loads(gh("api", "--method", "GET", "--paginate", "--slurp", endpoint))
    result = []
    for page in pages:
        values = page[key] if key is not None else page
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
            raise ValueError("GitHub collection response must contain JSON objects")
        result.extend(values)
    return result
