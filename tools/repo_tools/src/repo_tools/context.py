"""Resolve an explicit or discovered repository without installing tools or invoking Git."""

import tomllib
from pathlib import Path


def resolve_root(root: Path | None = None) -> Path:
    """Require version metadata and a uv workspace; explicit roots never fall back."""
    start = (root if root is not None else Path.cwd()).resolve()
    candidates = [start] if root is not None else [start, *start.parents]
    for candidate in candidates:
        if not (candidate / "version.txt").is_file():
            continue
        try:
            with (candidate / "pyproject.toml").open("rb") as file:
                config = tomllib.load(file)
            if isinstance(config.get("tool", {}).get("uv", {}).get("workspace"), dict):
                return candidate
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    raise ValueError(f"no repository workspace at {start}; select one with --project-root PATH")
