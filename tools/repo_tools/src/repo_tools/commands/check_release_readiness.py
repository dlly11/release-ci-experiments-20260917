"""Authorize releases from verified merges or explicitly selected fresh main validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from repo_tools.ci_validation import policy_at, profile_jobs, verify_profile
from repo_tools.github_api import api, items, repository_name
from repo_tools.github_checks import check_evidence, check_jobs, merged_pr


def check_run(
    run: dict[str, Any],
    repository: str,
    sha: str,
    workflow_id: int,
    *,
    event: str = "push",
) -> None:
    """Require successful CI with the specified event for the current main commit."""
    expected = {
        "workflow_id": workflow_id,
        "path": ".github/workflows/ci.yml",
        "event": event,
        "head_branch": "main",
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
    }
    for field, value in expected.items():
        if run.get(field) != value:
            raise ValueError(f"CI {field}: expected {value!r}, found {run.get(field)!r}")
    for field in ("repository", "head_repository"):
        actual = (run.get(field) or {}).get("full_name")
        if actual != repository:
            raise ValueError(f"CI {field}: expected {repository!r}, found {actual!r}")


def ready(
    event_name: str,
    event: dict[str, Any],
    repository: str,
    ref: str,
    sha: str,
    *,
    root: Path,
) -> bool:
    """Return false for obsolete automatic runs; reject all other ineligible runs."""
    automatic = event_name == "workflow_run"
    if event_name not in {"workflow_run", "workflow_dispatch"}:
        raise ValueError(f"unsupported release event: {event_name!r}")
    if not automatic and ref != "refs/heads/main":
        raise ValueError("manual releases must select the main branch")
    recovery = event.get("inputs", {}).get("recovery-run-id", "")
    if not isinstance(recovery, str) or (
        recovery and (automatic or not re.fullmatch(r"[1-9][0-9]*", recovery))
    ):
        raise ValueError("recovery-run-id must be a positive run ID on a manual Release dispatch")
    workflow = api(f"repos/{repository}/actions/workflows/ci.yml")
    workflow_id = workflow["id"]
    if automatic:
        run = event["workflow_run"]
        sha = run["head_sha"]
        check_run(run, repository, sha, workflow_id)

    branch_endpoint = f"repos/{repository}/branches/main"
    current_sha = api(branch_endpoint)["commit"]["sha"]
    if sha != current_sha:
        if automatic:
            print(f"Skipping stale release run for {sha}; main is now {current_sha}.")
            return False
        raise ValueError(
            f"manual run selected {sha}, but main is now {current_sha}; start a new run"
        )

    ci_event = "workflow_dispatch" if recovery else "push"
    query = urlencode({"branch": "main", "event": ci_event, "head_sha": sha, "per_page": 100})
    runs = api(f"repos/{repository}/actions/workflows/{workflow_id}/runs?{query}")["workflow_runs"]
    if not runs:
        raise ValueError(f"no {ci_event} CI run exists for main commit {sha}")
    # Do not filter by success: a newer failed or in-progress run invalidates an older success.
    latest = max(runs, key=lambda candidate: candidate["id"])
    if recovery and latest["id"] != int(recovery):
        raise ValueError("recovery-run-id must select the latest manual CI run for current main")
    latest = api(f"repos/{repository}/actions/runs/{latest['id']}")
    check_run(latest, repository, sha, workflow_id, event=ci_event)
    if recovery:
        merged_pr(repository, sha, root=root)
        evidence = check_evidence(
            repository, latest["id"], sha, sha, exact_checkout=True, root=root
        )
        if evidence["schema"] == 2:
            if evidence["profile"] != "full":
                raise ValueError("recovery requires full CI")
            verify_profile(repository, latest, evidence, sha, root)
        else:
            policy = policy_at(root, sha)
            if "validation" in policy:
                raise ValueError("profile-based recovery requires schema-2 evidence")
            check_jobs(repository, latest["id"], profile_jobs(policy, "full"))
    else:
        jobs = items(
            f"repos/{repository}/actions/runs/{latest['id']}/jobs?filter=latest&per_page=100",
            "jobs",
        )
        verification = [job for job in jobs if job["name"] == "Merged PR verification"]
        if (
            automatic
            and len(verification) == 1
            and verification[0]["status"] == "completed"
            and verification[0]["conclusion"] == "skipped"
        ):
            print("Skipping release: CI did not verify a merged PR (repository initialization).")
            return False
        if (
            len(verification) != 1
            or verification[0]["status"] != "completed"
            or verification[0]["conclusion"] != "success"
        ):
            raise ValueError("push CI must contain successful Merged PR verification")
    # Recheck after downloading evidence so an in-place rerun cannot authorize release.
    current_run = api(f"repos/{repository}/actions/runs/{latest['id']}")
    if current_run.get("run_attempt") != latest.get("run_attempt"):
        raise ValueError("a newer CI run attempt started during readiness validation")
    check_run(
        current_run,
        repository,
        sha,
        workflow_id,
        event=ci_event,
    )
    if recovery:
        newest = api(f"repos/{repository}/actions/workflows/{workflow_id}/runs?{query}")[
            "workflow_runs"
        ]
        if not newest or max(run["id"] for run in newest) != latest["id"]:
            raise ValueError("a newer manual CI run started during recovery validation")
    if api(branch_endpoint)["commit"]["sha"] != sha:
        if automatic:
            print("Skipping release because main advanced during the readiness check.")
            return False
        raise ValueError("main advanced during the readiness check; start a new run")
    print(f"Release ready: {ci_event} CI run {latest['id']} passed for main commit {sha}.")
    return True


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command arguments without performing any work."""


def execute(args: argparse.Namespace, *, root: Path) -> int:
    """Read GitHub's event context and emit a step output only after all checks pass."""
    try:
        repository = repository_name(os.environ["GITHUB_REPOSITORY"], root=root)
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        allowed = ready(
            os.environ["GITHUB_EVENT_NAME"],
            event,
            repository,
            os.environ["GITHUB_REF"],
            os.environ["GITHUB_SHA"],
            root=root,
        )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"ready={str(allowed).lower()}\n")
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"release readiness failed: {error}", file=sys.stderr)
        print(
            "Wait for verified push CI, or use fresh main CI with recovery-run-id. "
            "See docs/releases.md.",
            file=sys.stderr,
        )
        return 1
    return 0
