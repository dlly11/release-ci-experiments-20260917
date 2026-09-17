"""Select CI profiles and bind aggregate results to exact Git and workflow identities."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from repo_tools import github_checks as checks
from repo_tools.github_api import api, items
from repo_tools.release_changes import branch_at, managed_pr, release_changes, snapshot
from repo_tools.repository_metadata import git


@dataclass(frozen=True)
class ValidationResult:
    """Verified profile and authoritative run identity for reporting."""

    profile: str
    run_id: int
    run_attempt: int


def write_summary(
    stage: str,
    selected: dict[str, Any] | None = None,
    *,
    result: ValidationResult | None = None,
    error: str | None = None,
) -> None:
    """Append informational Markdown without changing the validation outcome."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        lines = [f"## {escape(stage)}", ""]
        if error is not None:
            lines.extend(["**Validation failed.**", "", f"<pre>{escape(error)}</pre>", ""])
        elif result is not None:
            lines.extend(["**Validation passed.**", ""])
        if isinstance(selected, dict):
            delegated = selected.get("role") == "delegate"
            profile = (
                result.profile
                if result
                else (
                    "Awaiting authoritative validation"
                    if delegated
                    else selected.get("profile", "Unknown")
                )
            )
            fields = {
                "Role": selected.get("role", "Unknown"),
                "Profile": profile,
                "Selection reason": selected.get("reason", "Unavailable"),
                "Base commit": selected.get("base_sha") or "Not applicable",
                "Head commit": selected.get("head_sha", "Unavailable"),
            }
            for label, value in fields.items():
                value = escape(str(value).replace("\r", " ").replace("\n", " "))
                lines.append(f"- {label}: <code>{value}</code>")
            if result is not None:
                server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
                repository = quote(str(selected["repository"]), safe="/")
                url = (
                    f"{server}/{repository}/actions/runs/{result.run_id}"
                    f"/attempts/{result.run_attempt}"
                )
                action = "Reused" if delegated else "Performed validation in"
                lines.append(
                    f'- {action} <a href="{escape(url, quote=True)}">authoritative run '
                    f"{result.run_id}, attempt {result.run_attempt}</a>."
                )
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n\n")
    except (OSError, KeyError, TypeError, ValueError) as summary_error:
        print(f"Could not write CI summary: {summary_error}", file=sys.stderr)


def policy_at(root: Path, revision: str) -> dict[str, Any]:
    return checks.validate_policy(
        json.loads(git("show", f"{revision}:{checks.POLICY.as_posix()}", root=root))
    )


def profile_jobs(policy: dict[str, Any], profile: str) -> set[str]:
    if "validation" in policy:
        return set(policy["validation"][profile])
    if profile != "full":
        raise ValueError("legacy policy supports only full CI")
    return {c["context"] for c in policy["protection"]["required_status_checks"]["checks"]} - {
        "Conventional PR title"
    }


def trusted_changes(root: Path, base: str, head: str) -> tuple[bool, str]:
    """Execute only base-revision classifier code; migration PRs use full CI."""
    files = git("ls-tree", "-r", "--name-only", base, "tools/repo_tools", root=root).splitlines()
    if "tools/repo_tools/src/repo_tools/ci_validation.py" not in files:
        return False, "base predates release-only CI"
    with snapshot(root, base, "tools/repo_tools") as baseline:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(baseline / "tools/repo_tools/run.py"),
                "--project-root",
                str(root),
                "check-ci-context",
                "--classify",
                "--base",
                base,
                "--head",
                head,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    value = json.loads(result.stdout)
    if type(value.get("release_only")) is not bool or not isinstance(value.get("reason"), str):
        raise ValueError("invalid base classifier response")
    return value["release_only"], value["reason"]


def verified_base(repository: str, base: str, workflow: int) -> dict[str, int] | None:
    """Bind eligibility to the latest successful verified main push, including its attempt."""
    query = urlencode({"branch": "main", "event": "push", "head_sha": base, "per_page": 100})
    endpoint = f"repos/{repository}/actions/workflows/{workflow}/runs?{query}"
    runs = items(endpoint, "workflow_runs")
    if not runs:
        return None
    run = api(f"repos/{repository}/actions/runs/{max(r['id'] for r in runs)}")
    expected = {
        "workflow_id": workflow,
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": base,
        "status": "completed",
        "conclusion": "success",
    }
    if any(run.get(k) != v for k, v in expected.items()):
        return None
    if any(
        (run.get(k) or {}).get("full_name") != repository for k in ("repository", "head_repository")
    ):
        raise ValueError("base CI belongs to another repository")
    jobs = items(
        f"repos/{repository}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100", "jobs"
    )
    matches = [j for j in jobs if j["name"] == "Merged PR verification"]
    if (
        len(matches) != 1
        or matches[0]["status"] != "completed"
        or matches[0]["conclusion"] != "success"
    ):
        return None
    latest = items(endpoint, "workflow_runs")
    current = api(f"repos/{repository}/actions/runs/{run['id']}")
    if (
        not latest
        or max(r["id"] for r in latest) != run["id"]
        or current.get("run_attempt") != run["run_attempt"]
        or any(current.get(key) != value for key, value in expected.items())
    ):
        return None
    return {"run_id": run["id"], "run_attempt": run["run_attempt"]}


def live_pr(repository: str, number: int, head: str) -> dict[str, Any]:
    pr = api(f"repos/{repository}/pulls/{number}")
    if (
        pr["state"] != "open"
        or pr["head"]["sha"] != head
        or pr["base"]["repo"]["full_name"] != repository
    ):
        raise ValueError("PR must be open in this repository at the expected head")
    return pr


def context(root: Path) -> dict[str, Any]:
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    repository = os.environ["GITHUB_REPOSITORY"]
    checkout = git("rev-parse", "HEAD", root=root).strip()
    if checkout != os.environ["GITHUB_SHA"]:
        raise ValueError("checkout does not match workflow SHA")
    result: dict[str, Any] = {
        "role": "authoritative",
        "profile": "full",
        "repository": repository,
        "head_sha": checkout,
        "checkout_sha": checkout,
        "base_sha": "",
        "pr_number": None,
        "base_verification": None,
        "reason": "ordinary full validation",
        "managed_release": False,
    }
    pr = None
    if event_name == "pull_request":
        pr = live_pr(repository, event["number"], event["pull_request"]["head"]["sha"])
        if pr["base"]["sha"] != event["pull_request"]["base"]["sha"]:
            raise ValueError("PR base advanced; rerun validation on the updated PR")
    elif event_name == "workflow_dispatch":
        inputs = event.get("inputs") or {}
        number, expected = inputs.get("release-pr-number", ""), inputs.get("expected-head", "")
        if bool(number) != bool(expected):
            raise ValueError("release-pr-number and expected-head must be provided together")
        if number:
            if expected != checkout or not str(number).isdigit() or int(number) < 1:
                raise ValueError("invalid release dispatch number or head")
            pr = live_pr(repository, int(number), checkout)
        elif os.environ["GITHUB_REF"] != "refs/heads/main":
            branch = os.environ["GITHUB_REF"].removeprefix("refs/heads/")
            candidates = items(
                f"repos/{repository}/pulls?"
                + urlencode(
                    {
                        "state": "open",
                        "head": f"{repository.split('/')[0]}:{branch}",
                        "per_page": 100,
                    }
                )
            )
            matches = [
                p
                for p in candidates
                if p["head"]["sha"] == checkout
                and (p["head"]["repo"] or {}).get("full_name") == repository
            ]
            if len(matches) > 1:
                raise ValueError("manual CI branch has multiple open PRs")
            if matches:
                pr = live_pr(repository, matches[0]["number"], checkout)
        if pr and (
            os.environ["GITHUB_REF"] != f"refs/heads/{pr['head']['ref']}"
            or (pr["head"]["repo"] or {}).get("full_name") != repository
        ):
            raise ValueError("manual validation must select the PR branch in this repository")
    elif event_name != "push" or event.get("before") not in {"0" * 40, "0" * 64}:
        raise ValueError("CI profile selection requires a PR, manual run, or initialization")
    if pr is None:
        return result
    result.update(head_sha=pr["head"]["sha"], base_sha=pr["base"]["sha"], pr_number=pr["number"])
    try:
        branch = branch_at(root, result["base_sha"])
    except (ValueError, KeyError, subprocess.CalledProcessError):
        result["reason"] = "unsupported release layout; using full CI"
        return result
    if not managed_pr(pr, repository, branch):
        if event_name == "workflow_dispatch" and (event.get("inputs") or {}).get(
            "release-pr-number"
        ):
            raise ValueError("release dispatch does not identify the configured managed PR")
        return result
    result["managed_release"] = True
    if event_name == "pull_request":
        result.update(role="delegate", reason="managed release CI uses an explicit dispatch")
        return result
    git("merge-base", "--is-ancestor", result["base_sha"], checkout, root=root)
    eligible, reason = trusted_changes(root, result["base_sha"], checkout)
    result["reason"] = reason
    if eligible:
        from repo_tools.commands.check_release_automation import eligible_pr

        eligible_pr(
            repository, pr["number"], branch, checkout, root=root, revision=result["base_sha"]
        )
        workflow = api(f"repos/{repository}/actions/workflows/ci.yml")["id"]
        proof = verified_base(repository, result["base_sha"], workflow)
        if proof:
            result.update(profile="release", base_verification=proof)
        else:
            result["reason"] = "base has no successful merged-PR verification; using full CI"
    return result


def check_selected_jobs(
    repository: str, run_id: int, policy: dict[str, Any], profile: str, *, gate: bool
) -> None:
    required = profile_jobs(policy, profile) | {"CI context"}
    if gate:
        required.add("CI result")
    inactive = (profile_jobs(policy, "full") | profile_jobs(policy, "release")) - required
    jobs = items(
        f"repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100", "jobs"
    )
    checks.validate_jobs(jobs, run_id, required)
    for job in jobs:
        if job["name"] in inactive and job["conclusion"] != "skipped":
            raise ValueError(f"unexpected active job for {profile} CI: {job['name']}")


def verify_profile(
    repository: str, run: dict[str, Any], evidence: dict[str, Any], commit: str, root: Path
) -> None:
    """Recompute reduced eligibility independently of the CI record's claim."""
    if (
        evidence["profile"] not in {"full", "release"}
        or evidence["run_attempt"] != run["run_attempt"]
    ):
        raise ValueError("CI profile or run attempt does not match")
    policy = policy_at(root, commit)
    check_selected_jobs(repository, run["id"], policy, evidence["profile"], gate=True)
    if evidence["profile"] == "release":
        base = evidence["base_sha"]
        git("merge-base", "--is-ancestor", base, commit, root=root)
        valid, reason = release_changes(root, base, commit)
        if not valid:
            raise ValueError(f"release CI evidence contains non-release changes: {reason}")
        proof = verified_base(repository, base, run["workflow_id"])
        if proof is None or proof != evidence["base_verification"]:
            raise ValueError("release base verification changed or is unavailable")
        if run["event"] != "workflow_dispatch" or run["head_branch"] != branch_at(root, base):
            raise ValueError("release evidence is not from the managed branch dispatch")


def newest_dispatch(repository: str, pr: dict[str, Any], workflow: int) -> dict[str, Any] | None:
    query = urlencode(
        {"head_sha": pr["head"]["sha"], "event": "workflow_dispatch", "per_page": 100}
    )
    runs = items(f"repos/{repository}/actions/workflows/{workflow}/runs?{query}", "workflow_runs")
    matches = [
        r
        for r in runs
        if r["event"] == "workflow_dispatch" and r["head_branch"] == pr["head"]["ref"]
    ]
    return (
        api(f"repos/{repository}/actions/runs/{max(r['id'] for r in matches)}") if matches else None
    )


def delegate(root: Path, selected: dict[str, Any], *, timeout: float = 35 * 60) -> ValidationResult:
    repository = selected["repository"]
    workflow = api(f"repos/{repository}/actions/workflows/ci.yml")["id"]
    deadline = time.monotonic() + timeout
    while True:
        pr = live_pr(repository, selected["pr_number"], selected["head_sha"])
        if pr["base"]["sha"] != selected["base_sha"] or not managed_pr(
            pr, repository, branch_at(root, selected["base_sha"])
        ):
            raise ValueError("release PR context changed while awaiting dispatch")
        run = newest_dispatch(repository, pr, workflow)
        if run and run["status"] == "completed":
            checks.check_ci_run(run, repository, pr, workflow)
            evidence = checks.check_evidence(
                repository, run["id"], selected["head_sha"], "HEAD", root=root
            )
            if evidence.get("schema") != 2 or evidence["base_sha"] != selected["base_sha"]:
                raise ValueError("delegation requires matching schema-2 base evidence")
            verify_profile(repository, run, evidence, "HEAD", root)
            latest = newest_dispatch(repository, pr, workflow)
            if (
                latest is None
                or latest["id"] != run["id"]
                or latest["run_attempt"] != run["run_attempt"]
            ):
                raise ValueError("a newer authoritative run or attempt started")
            checks.check_ci_run(latest, repository, pr, workflow)
            current = live_pr(repository, pr["number"], selected["head_sha"])
            if current["base"]["sha"] != selected["base_sha"]:
                raise ValueError("PR base advanced during delegated validation")
            print(f"Reused authoritative CI run {run['id']} ({evidence['profile']}).")
            return ValidationResult(evidence["profile"], run["id"], run["run_attempt"])
        if time.monotonic() >= deadline:
            raise ValueError(
                "authoritative CI did not finish; retry release preparation or its dispatched CI"
            )
        print("Waiting for authoritative release PR CI...", flush=True)
        time.sleep(min(30, max(0, deadline - time.monotonic())))


def finish(root: Path, selected: dict[str, Any], output: Path) -> ValidationResult:
    repository = os.environ["GITHUB_REPOSITORY"]
    if selected["repository"] != repository or selected["checkout_sha"] != os.environ["GITHUB_SHA"]:
        raise ValueError("CI context does not match this workflow")
    if git("rev-parse", "HEAD", root=root).strip() != selected["checkout_sha"]:
        raise ValueError("gate checkout does not match CI context")
    if selected["role"] == "delegate":
        return delegate(root, selected)
    if selected["role"] != "authoritative":
        raise ValueError("unknown CI role")
    if selected["pr_number"]:
        pr = live_pr(repository, selected["pr_number"], selected["head_sha"])
        if pr["base"]["sha"] != selected["base_sha"]:
            raise ValueError("PR base changed during CI")
    policy = checks.load_policy(root=root)
    check_selected_jobs(
        repository, int(os.environ["GITHUB_RUN_ID"]), policy, selected["profile"], gate=False
    )
    if selected["profile"] == "release":
        valid, reason = trusted_changes(root, selected["base_sha"], selected["head_sha"])
        if not valid:
            raise ValueError(f"release classification changed: {reason}")
        workflow = api(f"repos/{repository}/actions/workflows/ci.yml")["id"]
        if (
            verified_base(repository, selected["base_sha"], workflow)
            != selected["base_verification"]
        ):
            raise ValueError("base CI changed during validation")
    if os.environ["GITHUB_EVENT_NAME"] != "push":
        checks.record(output, root=root, context=selected)
    print(f"CI result: {selected['profile']} validation passed.")
    return ValidationResult(
        selected["profile"], int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"])
    )
