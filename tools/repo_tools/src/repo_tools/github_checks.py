"""Shared read-only GitHub policy and CI evidence checks."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from repo_tools.conventional_commits import check_message
from repo_tools.github_api import api, gh, items, repository_name
from repo_tools.repository_metadata import git

POLICY = Path("tools/github/repository-policy.json")


def check_set(checks: list[dict[str, Any]]) -> set[str]:
    """Compare check identities independently of their API ordering."""
    return {f"{check['context']} (app_id={check.get('app_id')})" for check in checks}


def differences(expected: dict[str, Any], actual: dict[str, Any], prefix: str) -> list[str]:
    """Compare only managed keys and report all discrepancies together."""
    errors = []
    for key, wanted in expected.items():
        path = f"{prefix}.{key}"
        found = actual.get(key)
        if isinstance(wanted, dict) and isinstance(found, dict):
            errors.extend(differences(wanted, found, path))
        elif key == "checks" and isinstance(wanted, list) and isinstance(found, list):
            wanted_checks, found_checks = check_set(wanted), check_set(found)
            if wanted_checks != found_checks:
                errors.append(
                    f"{path}: expected {sorted(wanted_checks)!r}, found {sorted(found_checks)!r}"
                )
        elif type(wanted) is not type(found) or wanted != found:
            errors.append(f"{path}: expected {wanted!r}, found {found!r}")
    return errors


def load_policy(*, root: Path) -> dict[str, Any]:
    """Reject incomplete policy files before attempting any GitHub reads."""
    policy = json.loads((root / POLICY).read_text(encoding="utf-8"))
    return validate_policy(policy)


def validate_policy(policy: Any) -> dict[str, Any]:
    """Validate current and legacy policy formats."""
    if not isinstance(policy, dict) or set(policy) not in (
        {"repository", "protection"},
        {"repository", "protection", "validation"},
    ):
        raise ValueError("policy must contain repository and protection objects")
    if not all(isinstance(value, dict) and value for value in policy.values()):
        raise ValueError("policy sections must be nonempty objects")
    branch = policy["repository"].get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise ValueError("policy must specify a default_branch")
    checks = policy["protection"]["required_status_checks"]["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("policy must specify a nonempty required check list")
    for check in checks:
        if (
            not isinstance(check, dict)
            or set(check) != {"context", "app_id"}
            or not isinstance(check["context"], str)
            or not check["context"]
            or type(check["app_id"]) is not int
            or check["app_id"] <= 0
        ):
            raise ValueError("each required check must have a context and positive integer app_id")
    if len(check_set(checks)) != len(checks):
        raise ValueError("policy contains duplicate required checks")
    if "validation" in policy:
        profiles = policy["validation"]
        if set(profiles) != {"full", "release"}:
            raise ValueError("validation must define full and release profiles")
        for names in profiles.values():
            if (
                not isinstance(names, list)
                or not names
                or any(not isinstance(name, str) or not name for name in names)
                or len(set(names)) != len(names)
                or {"CI context", "CI result", "Conventional PR title"} & set(names)
            ):
                raise ValueError("validation profiles must list unique quality job names")
        if set(profiles["full"]) & set(profiles["release"]):
            raise ValueError("validation profiles must use distinct jobs")
        if {c["context"] for c in checks} != {"CI result", "Conventional PR title"}:
            raise ValueError("profile-based CI requires CI result and Conventional PR title")
    return policy


ARTIFACT = "pr-validation"


def record(path: Path, *, root: Path | None = None, context: dict[str, Any] | None = None) -> None:
    """Record the actual checkout used by this CI run, including synthetic PR merges."""
    event_name = os.environ["GITHUB_EVENT_NAME"]
    if event_name not in {"pull_request", "workflow_dispatch"}:
        raise ValueError("validation records can only be produced by PR or manual CI")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    head = (
        event["pull_request"]["head"]["sha"]
        if event_name == "pull_request"
        else os.environ["GITHUB_SHA"]
    )
    checkout = git("rev-parse", "HEAD", root=root).strip()
    if checkout != os.environ["GITHUB_SHA"]:
        raise ValueError("checkout does not match the workflow commit")
    git("diff", "--exit-code", "HEAD", "--", root=root)
    data = {
        "schema": 1,
        "repository": repository_name(os.environ["GITHUB_REPOSITORY"], root=root),
        "run_id": int(os.environ["GITHUB_RUN_ID"]),
        "head_sha": head,
        "checkout_sha": checkout,
        "tree_sha": git("rev-parse", "HEAD^{tree}", root=root).strip(),
    }
    if context is not None:
        if context["head_sha"] != head or context["checkout_sha"] != checkout:
            raise ValueError("validation context does not match tested checkout")
        data.update(
            schema=2,
            profile=context["profile"],
            base_sha=context["base_sha"],
            base_verification=context["base_verification"],
            run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded tested tree {data['tree_sha']} for CI run {data['run_id']}.")


def validation_record(repository: str, run_id: int) -> dict[str, Any]:
    """Read only the JSON record from the selected workflow run's artifact."""
    with tempfile.TemporaryDirectory(prefix="pr-validation-") as directory:
        gh(
            "run",
            "download",
            str(run_id),
            "--repo",
            repository,
            "--name",
            ARTIFACT,
            "--dir",
            directory,
        )
        path = Path(directory) / "validation.json"
        if path.stat().st_size > 65536:
            raise ValueError("PR validation record is unexpectedly large")
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("PR validation record must be a JSON object")
    return data


def check_ci_run(
    run: dict[str, Any], repository: str, pr: dict[str, Any], workflow_id: int
) -> None:
    """Require a successful run of this repository's CI for the original PR head."""
    expected = {
        "workflow_id": workflow_id,
        "path": ".github/workflows/ci.yml",
        "head_sha": pr["head"]["sha"],
        "status": "completed",
        "conclusion": "success",
    }
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError(f"PR CI {key}: expected {value!r}, found {run.get(key)!r}")
    if run["repository"]["full_name"] != repository:
        raise ValueError("PR CI ran in a different repository")
    # GitHub clears run.pull_requests after merging. Bind the immutable head and recorded tree
    # instead, while checking the original branch and the repository that ran the workflow.
    if run["head_branch"] != pr["head"]["ref"]:
        raise ValueError("PR CI ran on a different head branch")
    if run["event"] == "workflow_dispatch":
        if (pr["head"]["repo"] or {}).get("full_name") != repository:
            raise ValueError("manual CI must run on the PR head branch in this repository")
    elif run["event"] != "pull_request":
        raise ValueError(f"unsupported PR CI event: {run['event']!r}")


def associated_prs(repository: str, commit: str) -> list[dict[str, Any]]:
    """Find merged GitHub PRs that introduced a commit to main."""
    return [
        pr
        for pr in items(f"repos/{repository}/commits/{commit}/pulls?per_page=100")
        if pr.get("merged_at")
        and pr["base"]["ref"] == "main"
        and pr["base"]["repo"]["full_name"] == repository
    ]


def merged_pr(
    repository: str, commit: str, *, root: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Validate a PR's final commit and return its first-parent integration, oldest first."""
    if git("rev-parse", "--is-shallow-repository", root=root).strip() == "true":
        raise ValueError(
            "merged PR validation requires full Git history; "
            "use checkout fetch-depth: 0 or run git fetch --unshallow in the target checkout"
        )
    parents = git("show", "--no-patch", "--format=%P", commit, "--", root=root).split()
    if len(parents) not in {1, 2}:
        raise ValueError(f"{commit}: expected a one-parent commit or two-parent merge commit")
    if not check_message(
        git("show", "--no-patch", "--format=%B", commit, "--", root=root), commit[:12]
    ):
        raise ValueError("merged commit subject is not conventional")
    candidates = associated_prs(repository, commit)
    if len(candidates) != 1 or candidates[0].get("merge_commit_sha") != commit:
        raise ValueError(
            f"{commit}: expected exactly one merged PR targeting main at its final commit"
        )
    pr = api(f"repos/{repository}/pulls/{candidates[0]['number']}")
    if pr.get("merge_commit_sha") != commit:
        raise ValueError(f"{commit}: merged PR final commit changed during verification")
    integration = [commit]
    if len(parents) == 2:
        if parents[1] != pr["head"]["sha"]:
            raise ValueError(f"{commit}: merge second parent does not match the PR head")
        # These commits remain in main's history. Check them during recovery too, where
        # fresh manual CI on main has no new commit range to lint.
        introduced = git("rev-list", f"{parents[0]}..{parents[1]}", "--", root=root).splitlines()
        for sha in introduced:
            if not check_message(
                git("show", "--no-patch", "--format=%B", sha, "--", root=root), sha[:12]
            ):
                raise ValueError("merged PR commit subject is not conventional")
    else:
        # GitHub records the last rebased SHA as merge_commit_sha. Its commit-to-PR
        # endpoint identifies the preceding rewritten commits, without relying on
        # original SHAs, commit counts, messages, or patch equivalence to infer membership.
        parent = parents[0]
        while True:
            preceding = associated_prs(repository, parent)
            if not any(candidate["number"] == pr["number"] for candidate in preceding):
                break
            if len(preceding) != 1 or preceding[0].get("merge_commit_sha") != commit:
                raise ValueError(f"{parent}: ambiguous rebased PR association")
            parents = git("show", "--no-patch", "--format=%P", parent, "--", root=root).split()
            if len(parents) != 1:
                raise ValueError(f"{parent}: rebased PR commits must each have one parent")
            if not check_message(
                git("show", "--no-patch", "--format=%B", parent, "--", root=root), parent[:12]
            ):
                raise ValueError("rebased PR commit subject is not conventional")
            integration.append(parent)
            parent = parents[0]
    return pr, list(reversed(integration))


def check_jobs(repository: str, run_id: int, required: set[str]) -> None:
    """Require every quality job to have actually succeeded, including partial reruns."""
    jobs = items(
        f"repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100", "jobs"
    )
    validate_jobs(jobs, run_id, required)


def validate_jobs(jobs: list[dict[str, Any]], run_id: int, required: set[str]) -> None:
    """Validate required jobs against one fetched collection."""
    for name in sorted(required):
        matches = [job for job in jobs if job["name"] == name]
        if (
            len(matches) != 1
            or matches[0]["status"] != "completed"
            or matches[0]["conclusion"] != "success"
        ):
            raise ValueError(f"CI run {run_id}: required CI job {name!r} did not pass")


def check_evidence(
    repository: str,
    run_id: int,
    head: str,
    commit: str,
    *,
    exact_checkout: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Bind the recorded tested tree to a commit; recovery also binds the checkout SHA."""
    evidence = validation_record(repository, run_id)
    if type(evidence.get("schema")) is not int or evidence["schema"] not in {1, 2}:
        raise ValueError("unsupported CI evidence schema")
    if evidence["schema"] == 2 and (
        evidence.get("profile") not in {"full", "release"}
        or type(evidence.get("run_attempt")) is not int
        or evidence["run_attempt"] < 1
        or not isinstance(evidence.get("base_sha"), str)
        or "base_verification" not in evidence
    ):
        raise ValueError("invalid schema-2 CI evidence")
    if evidence["schema"] == 2:
        proof = evidence["base_verification"]
        if evidence["profile"] == "release":
            if (
                not evidence["base_sha"]
                or not isinstance(proof, dict)
                or set(proof) != {"run_id", "run_attempt"}
                or any(type(value) is not int or value < 1 for value in proof.values())
            ):
                raise ValueError("invalid release base verification evidence")
        elif proof is not None:
            raise ValueError("full CI must not claim reduced base verification")
    expected = {
        "repository": repository,
        "run_id": run_id,
        "head_sha": head,
        "tree_sha": git("rev-parse", f"{commit}^{{tree}}", root=root).strip(),
    }
    if exact_checkout:
        expected["checkout_sha"] = commit
    for key, value in expected.items():
        if type(evidence.get(key)) is not type(value) or evidence.get(key) != value:
            raise ValueError(f"CI run {run_id}: validation {key} does not match the commit/run")
    return evidence


def verify_commit(
    repository: str, commit: str, workflow_id: int, *, root: Path | None = None
) -> list[str]:
    """Bind a PR's final tree to successful CI and return its integrated first-parent commits."""
    pr, integration = merged_pr(repository, commit, root=root)
    from repo_tools.ci_validation import policy_at, profile_jobs, verify_profile
    from repo_tools.release_changes import branch_at, managed_pr

    root = root or Path.cwd()
    predecessor = git("rev-parse", f"{integration[0]}^", root=root).strip()
    tested_policy = policy_at(root, commit)
    modern = "validation" in tested_policy
    managed = False
    if modern:
        with contextlib.suppress(ValueError, KeyError):
            managed = managed_pr(pr, repository, branch_at(root, predecessor))
    query = urlencode({"head_sha": pr["head"]["sha"], "per_page": 100})
    endpoint = f"repos/{repository}/actions/workflows/{workflow_id}/runs?{query}"

    def newest_run_id() -> int:
        runs = [
            run
            for run in items(endpoint, "workflow_runs")
            if run["event"]
            in ({"workflow_dispatch"} if managed else {"pull_request", "workflow_dispatch"})
            and run["head_branch"] == pr["head"]["ref"]
        ]
        if not runs:
            raise ValueError(f"PR #{pr['number']}: no PR CI run found")
        return max(run["id"] for run in runs)

    run = api(f"repos/{repository}/actions/runs/{newest_run_id()}")
    check_ci_run(run, repository, pr, workflow_id)
    evidence = check_evidence(repository, run["id"], pr["head"]["sha"], commit, root=root)
    if evidence["schema"] == 2:
        if evidence["profile"] == "release" and evidence["base_sha"] != predecessor:
            raise ValueError("release CI base does not match the integration predecessor")
        verify_profile(repository, run, evidence, commit, root)
    else:
        if modern:
            raise ValueError("profile-based CI requires schema-2 evidence")
        check_jobs(repository, run["id"], profile_jobs(tested_policy, "full"))
    # A re-run may have started while the evidence was downloaded.
    current = api(f"repos/{repository}/actions/runs/{run['id']}")
    check_ci_run(current, repository, pr, workflow_id)
    if current.get("run_attempt") != run.get("run_attempt"):
        raise ValueError("a newer CI run attempt started during merge verification")
    if newest_run_id() != run["id"]:
        raise ValueError("a newer PR CI run started during merge verification")
    print(f"Verified {commit[:12]} matches PR #{pr['number']}'s tested tree, CI run {run['id']}.")
    return integration
