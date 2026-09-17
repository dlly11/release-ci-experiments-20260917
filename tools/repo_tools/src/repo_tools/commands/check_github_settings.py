"""Audit managed GitHub settings against the checked-in policy without changing them."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

from repo_tools.github_api import api, items, repository_name
from repo_tools.github_checks import differences, load_policy


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""
    parser.add_argument("--repo", help="OWNER/REPO (default: current checkout's GitHub repository)")
    parser.add_argument(
        "--extended",
        action="store_true",
        help="also report rules, Actions, auto-merge, and CODEOWNERS",
    )


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Return 0 for matching settings, 1 for drift, and 2 for an unavailable audit."""
    try:
        policy = load_policy(root=root)
        repository = repository_name(args.repo, root=root)
        branch = policy["repository"]["default_branch"]
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"cannot audit GitHub settings: {error}", file=sys.stderr)
        return 2
    errors: list[str] = []
    unavailable: list[str] = []
    try:
        actual = api(f"repos/{repository}")
        errors.extend(differences(policy["repository"], actual, "repository"))
        if args.extended:
            enabled = actual["allow_auto_merge"]
            if type(enabled) is not bool:
                raise ValueError("auto-merge setting must be boolean")
            print(f"Repository auto-merge: {'enabled' if enabled else 'disabled'} (informational)")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        unavailable.append(f"repository settings: {error}")
    try:
        endpoint = f"repos/{repository}/branches/{quote(branch, safe='')}"
        branch_info = api(endpoint)
        if branch_info["protected"]:
            errors.extend(
                differences(policy["protection"], api(f"{endpoint}/protection"), "protection")
            )
        else:
            errors.append(f"protection: expected protected branch {branch!r}, found unprotected")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        unavailable.append(f"classic branch protection: {error}")
    if args.extended:
        for section in ("rules", "actions", "codeowners"):
            try:
                errors.extend(extended_section(section, repository, branch))
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
                unavailable.append(f"{section}: {error}")
    for error in errors:
        print(f"GitHub audit problem: {error}", file=sys.stderr)
    for error in unavailable:
        print(f"cannot audit GitHub settings: {error}", file=sys.stderr)
    if unavailable:
        return 2
    if errors:
        return 1
    print(f"Managed GitHub settings match policy for {repository}. No settings were changed.")
    return 0


def extended_section(section: str, repository: str, branch: str) -> list[str]:
    """Read independent setup diagnostics without claiming ruleset policy equivalence."""
    prefix = f"repos/{repository}"
    if section == "rules":
        rules = items(f"{prefix}/rules/branches/{quote(branch, safe='')}?per_page=100")
        print(
            f"Active branch rules: {len(rules)} (informational; not compared with classic policy)"
        )
        for rule in rules:
            print(
                f"  {rule['type']}: {rule['ruleset_source_type']} {rule['ruleset_source']} "
                f"(ruleset {rule['ruleset_id']}): "
                f"{json.dumps(rule.get('parameters', {}), sort_keys=True)}"
            )
    elif section == "actions":
        permissions = api(f"{prefix}/actions/permissions/workflow")
        print(
            f"Actions default workflow permissions: {permissions['default_workflow_permissions']}"
        )
        allowed = permissions["can_approve_pull_request_reviews"]
        if type(allowed) is not bool:
            raise ValueError("Actions PR permission must be boolean")
        print(f"Actions create/approve PRs setting: {'enabled' if allowed else 'disabled'}")
        print(
            "  Informational: organization policy and the selected release credential also apply."
        )
    elif section == "codeowners":
        errors = api(f"{prefix}/codeowners/errors?ref={quote(branch, safe='')}")["errors"]
        if not isinstance(errors, list):
            raise ValueError("CODEOWNERS errors must be a list")
        print(f"GitHub CODEOWNERS errors on {branch}: {len(errors)}")
        return [
            f"CODEOWNERS {error['path']}:{error['line']}: {error['message']}" for error in errors
        ]
    return []
