"""CI gates must bind exact runs, profiles, attempts, and Git contents."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from repo_tools import ci_validation as ci
from repo_tools import cli
from repo_tools import github_checks as checks
from repo_tools.commands import check_release_automation as automation
from repo_tools.release_changes import release_branch

REPOSITORY = "owner/project"
POLICY = {"validation": {"full": ["Tests", "Build"], "release": ["Release validation"]}}


@pytest.fixture
def ci_state(tmp_path, monkeypatch):
    branch = release_branch(
        {"packages": {".": {"release-type": "simple", "package-name": "sample"}}}
    )
    pr = {
        "number": 1,
        "state": "open",
        "draft": False,
        "title": "chore(main): release 1.3.0",
        "labels": [{"name": "autorelease: pending"}],
        "base": {"sha": "base", "ref": "main", "repo": {"full_name": REPOSITORY}},
        "head": {"sha": "head", "ref": branch, "repo": {"full_name": REPOSITORY}},
    }
    run: dict[str, Any] = {
        "id": 100,
        "run_attempt": 1,
        "workflow_id": 42,
        "path": ".github/workflows/ci.yml",
        "status": "completed",
        "conclusion": "success",
        "head_sha": "head",
        "head_branch": branch,
        "event": "workflow_dispatch",
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ["CI context", "CI result", "Tests", "Build"]
    ]
    state = {
        "pr": pr,
        "run": run,
        "jobs": jobs,
        "proof": {"run_id": 90, "run_attempt": 1},
        "eligible": True,
    }

    def api(endpoint):
        if "/pulls/" in endpoint:
            return state["pr"]
        if endpoint.endswith("/ci.yml"):
            return {"id": 42}
        return state["run"]

    def items(endpoint, key=None):
        if key == "jobs":
            return state["jobs"]
        if "/pulls?" in endpoint:
            return [state["pr"]]
        return [state["run"]]

    monkeypatch.setattr(ci, "api", api)
    monkeypatch.setattr(ci, "items", items)
    monkeypatch.setattr(checks, "items", items)
    monkeypatch.setattr(automation, "api", api)
    monkeypatch.setattr(ci, "git", lambda *args, **kw: "head\n" if args[0] == "rev-parse" else "")
    monkeypatch.setattr(ci, "branch_at", lambda *args: branch)
    monkeypatch.setattr(automation, "branch_at", lambda *args: branch)
    monkeypatch.setattr(ci, "trusted_changes", lambda *args: (state["eligible"], "classification"))
    monkeypatch.setattr(ci, "release_changes", lambda *args: (state["eligible"], "classification"))
    monkeypatch.setattr(ci, "verified_base", lambda *args: state["proof"])
    monkeypatch.setattr(ci, "policy_at", lambda *args: POLICY)
    monkeypatch.setattr(checks, "load_policy", lambda **kw: POLICY)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"release-pr-number": "1", "expected-head": "head"}}))
    state["event"] = event
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_SHA", "head")
    monkeypatch.setenv("GITHUB_REF", f"refs/heads/{branch}")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    return state


def test_release_dispatch_selects_reduced(ci_state, tmp_path):
    selected = ci.context(tmp_path)
    assert selected["profile"] == "release"
    assert selected["role"] == "authoritative"
    assert selected["base_verification"] == ci_state["proof"]


@pytest.mark.parametrize("fallback", ["diff", "proof"])
def test_full_fallback(ci_state, tmp_path, fallback):
    ci_state["eligible" if fallback == "diff" else "proof"] = False if fallback == "diff" else None
    assert ci.context(tmp_path)["profile"] == "full"


def test_managed_pr_event_delegates(ci_state, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    ci_state["event"].write_text(json.dumps({"number": 1, "pull_request": ci_state["pr"]}))
    assert ci.context(tmp_path)["role"] == "delegate"


def test_ordinary_pr_remains_full(ci_state, tmp_path, monkeypatch):
    ci_state["pr"]["head"]["ref"] = "feature"
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    ci_state["event"].write_text(json.dumps({"number": 1, "pull_request": ci_state["pr"]}))
    assert ci.context(tmp_path)["profile"] == "full"
    assert ci.context(tmp_path)["role"] == "authoritative"


def test_main_recovery_remains_full(ci_state, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    ci_state["event"].write_text("{}")
    assert ci.context(tmp_path)["profile"] == "full"


@pytest.mark.parametrize(
    "change",
    [
        "input-head",
        "missing-input",
        "closed",
        "head",
        "base-repo",
        "branch",
        "ref",
        "draft",
        "title",
        "label",
        "checkout",
    ],
)
def test_invalid_context_fails(ci_state, tmp_path, monkeypatch, change):
    if change == "input-head":
        ci_state["event"].write_text(
            json.dumps({"inputs": {"release-pr-number": "1", "expected-head": "other"}})
        )
    elif change == "missing-input":
        ci_state["event"].write_text(json.dumps({"inputs": {"release-pr-number": "1"}}))
    elif change == "closed":
        ci_state["pr"]["state"] = "closed"
    elif change == "head":
        ci_state["pr"]["head"]["sha"] = "other"
    elif change == "base-repo":
        ci_state["pr"]["base"]["repo"]["full_name"] = "other/repo"
    elif change == "branch":
        ci_state["pr"]["head"]["ref"] = "other"
    elif change == "ref":
        monkeypatch.setenv("GITHUB_REF", "refs/heads/other")
    elif change == "checkout":
        monkeypatch.setenv("GITHUB_SHA", "other")
    elif change == "label":
        ci_state["pr"]["labels"] = []
    else:
        ci_state["pr"][change] = True if change == "draft" else "feat: unrelated"
    with pytest.raises(ValueError):
        ci.context(tmp_path)


@pytest.mark.parametrize("conclusion", ["failure", "skipped", "cancelled", "timed_out", None])
def test_gate_rejects_required_job(ci_state, conclusion):
    ci_state["jobs"][-1]["conclusion"] = conclusion
    with pytest.raises(ValueError, match="did not pass"):
        ci.check_selected_jobs(REPOSITORY, 100, POLICY, "full", gate=True)


@pytest.mark.parametrize("change", ["missing", "duplicate", "inactive"])
def test_gate_rejects_wrong_job_set(ci_state, change):
    if change == "missing":
        ci_state["jobs"].pop()
    elif change == "duplicate":
        ci_state["jobs"].append(ci_state["jobs"][-1].copy())
    else:
        ci_state["jobs"].append(
            {"name": "Release validation", "conclusion": "success", "status": "completed"}
        )
    with pytest.raises(ValueError):
        ci.check_selected_jobs(REPOSITORY, 100, POLICY, "full", gate=True)


def test_gate_allows_skipped_inactive_profile(ci_state):
    ci_state["jobs"].append(
        {"name": "Release validation", "conclusion": "skipped", "status": "completed"}
    )
    ci.check_selected_jobs(REPOSITORY, 100, POLICY, "full", gate=True)


def test_profile_rechecks_attempt(ci_state, tmp_path):
    with pytest.raises(ValueError, match="attempt"):
        ci.verify_profile(
            REPOSITORY, ci_state["run"], {"profile": "full", "run_attempt": 2}, "HEAD", tmp_path
        )


@pytest.mark.parametrize("change", ["diff", "proof", "branch", "event"])
def test_reduced_evidence_rechecks_eligibility(ci_state, tmp_path, change):
    evidence = {
        "profile": "release",
        "run_attempt": 1,
        "base_sha": "base",
        "base_verification": copy.deepcopy(ci_state["proof"]),
    }
    ci_state["jobs"] = [j for j in ci_state["jobs"] if j["name"].startswith("CI ")]
    ci_state["jobs"].append(
        {"name": "Release validation", "status": "completed", "conclusion": "success"}
    )
    ci.verify_profile(REPOSITORY, ci_state["run"], evidence, "HEAD", tmp_path)
    if change == "diff":
        ci_state["eligible"] = False
    elif change == "proof":
        ci_state["proof"]["run_attempt"] = 2
    else:
        ci_state["run"]["head_branch" if change == "branch" else "event"] = "other"
    with pytest.raises(ValueError):
        ci.verify_profile(REPOSITORY, ci_state["run"], evidence, "HEAD", tmp_path)


def test_delegate_reuses_dispatch(ci_state, tmp_path, monkeypatch):
    selected = ci.context(tmp_path)
    evidence = {"schema": 2, "profile": "full", "run_attempt": 1, "base_sha": "base"}
    monkeypatch.setattr(checks, "check_evidence", lambda *args, **kw: evidence)
    ci.delegate(tmp_path, selected, timeout=0)
    ci_state["run"]["conclusion"] = "failure"
    with pytest.raises(ValueError, match="conclusion"):
        ci.delegate(tmp_path, selected, timeout=0)


def test_delegate_timeout(ci_state, tmp_path):
    selected = ci.context(tmp_path)
    ci_state["run"]["status"] = "in_progress"
    with pytest.raises(ValueError, match="did not finish"):
        ci.delegate(tmp_path, selected, timeout=0)


def test_no_record_when_gate_fails(ci_state, tmp_path):
    selected = ci.context(tmp_path)
    with pytest.raises(ValueError, match="did not pass"):
        ci.finish(tmp_path, selected, tmp_path / "validation.json")
    assert not (tmp_path / "validation.json").exists()


def test_cli_classify_requires_revisions(tmp_path):
    assert cli.main(["check-ci-context", "--classify"]) == 1


def test_cli_gate_without_context_fails(monkeypatch):
    monkeypatch.delenv("CI_CONTEXT", raising=False)
    assert cli.main(["check-ci-result"]) == 1


@pytest.mark.parametrize("change", [None, "schema", "attempt", "gate", "skipped", "base"])
def test_modern_merge_evidence(merge_context, monkeypatch, change):
    module, state = merge_context
    policy = {"validation": {"full": sorted(state["required"]), "release": ["Release validation"]}}
    monkeypatch.setattr(ci, "policy_at", lambda *args: policy)
    monkeypatch.setattr(ci, "items", module.items)
    from repo_tools import release_changes as changes

    monkeypatch.setattr(changes, "branch_at", lambda *args: "release-please--branches--main")
    state["runs"][0]["run_attempt"] = 1
    state["jobs"].extend(
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ["CI context", "CI result"]
    )
    state["evidence"].update(
        schema=2, profile="full", run_attempt=1, base_sha=state["base"], base_verification=None
    )
    if change == "schema":
        state["evidence"]["schema"] = 1
    elif change == "attempt":
        state["evidence"]["run_attempt"] = 2
    elif change == "gate":
        state["jobs"].pop()
    elif change == "skipped":
        state["jobs"][0]["conclusion"] = "skipped"
    elif change == "base":
        state["evidence"].update(
            profile="release", base_sha="wrong", base_verification={"run_id": 90, "run_attempt": 1}
        )
    assert cli.main(state["arguments"]) == (1 if change else 0)


@pytest.mark.parametrize("change", [None, "reduced", "attempt", "schema"])
def test_modern_recovery_requires_full(recovery_context, monkeypatch, change):
    module, state = recovery_context
    policy = {"validation": {"full": sorted(state["required"]), "release": ["Release validation"]}}
    monkeypatch.setattr(module, "policy_at", lambda *args: policy)
    monkeypatch.setattr(ci, "policy_at", lambda *args: policy)
    monkeypatch.setattr(ci, "items", checks.items)
    state["runs"][0]["run_attempt"] = 1
    state["jobs"].extend(
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ["CI context", "CI result"]
    )
    state["evidence"].update(
        schema=2, profile="full", run_attempt=1, base_sha="", base_verification=None
    )
    if change == "reduced":
        state["evidence"].update(
            profile="release", base_sha="base", base_verification={"run_id": 90, "run_attempt": 1}
        )
    elif change == "attempt":
        state["evidence"]["run_attempt"] = 2
    elif change == "schema":
        state["evidence"]["schema"] = 1
    arguments = ("workflow_dispatch", state["event"], REPOSITORY, "refs/heads/main", state["merge"])
    if change:
        with pytest.raises(ValueError):
            module.ready(*arguments, root=Path.cwd())
    else:
        assert module.ready(*arguments, root=Path.cwd())


@pytest.mark.parametrize("change", [None, "missing", "pending", "job", "repo", "attempt", "newer"])
def test_base_verification_races(monkeypatch, change):
    run: dict[str, Any] = {
        "id": 90,
        "run_attempt": 1,
        "workflow_id": 42,
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": "base",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }
    reads = 0

    def api(endpoint):
        nonlocal reads
        reads += 1
        value = copy.deepcopy(run)
        if change == "pending":
            value["status"] = "in_progress"
        elif change == "repo":
            value["repository"]["full_name"] = "wrong/repo"
        elif change == "attempt" and reads > 1:
            value["run_attempt"] = 2
        return value

    def items(endpoint, key=None):
        if key == "jobs":
            return [
                {
                    "name": "Merged PR verification",
                    "status": "completed",
                    "conclusion": "skipped" if change == "job" else "success",
                }
            ]
        if change == "missing":
            return []
        return [{"id": 91 if change == "newer" and reads else 90}]

    monkeypatch.setattr(ci, "api", api)
    monkeypatch.setattr(ci, "items", items)
    if change == "repo":
        with pytest.raises(ValueError, match="another repository"):
            ci.verified_base(REPOSITORY, "base", 42)
    else:
        assert ci.verified_base(REPOSITORY, "base", 42) == (
            None if change else {"run_id": 90, "run_attempt": 1}
        )


@pytest.mark.parametrize("change", ["schema", "base", "newer", "attempt", "stale"])
def test_delegate_rejects_stale_evidence(ci_state, tmp_path, monkeypatch, change):
    selected = ci.context(tmp_path)
    evidence = {"schema": 2, "profile": "full", "run_attempt": 1, "base_sha": "base"}
    if change == "schema":
        evidence["schema"] = 1
    elif change == "base":
        evidence["base_sha"] = "other"
    elif change == "stale":
        ci_state["pr"]["base"]["sha"] = "other"
    monkeypatch.setattr(checks, "check_evidence", lambda *args, **kw: evidence)
    run = copy.deepcopy(ci_state["run"])
    later = copy.deepcopy(run)
    if change == "newer":
        later["id"] += 1
    elif change == "attempt":
        later["run_attempt"] += 1
    runs = iter([run, later])
    monkeypatch.setattr(ci, "newest_dispatch", lambda *args: next(runs))
    with pytest.raises(ValueError):
        ci.delegate(tmp_path, selected, timeout=0)


def test_gate_records_after_reduced_jobs_pass(ci_state, tmp_path, monkeypatch):
    selected = ci.context(tmp_path)
    ci_state["jobs"] = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ["CI context", "Release validation"]
    ]
    recorded = []
    monkeypatch.setattr(checks, "record", lambda *args, **kw: recorded.append(kw["context"]))
    ci.finish(tmp_path, selected, tmp_path / "validation.json")
    assert recorded == [selected]
    ci_state["eligible"] = False
    with pytest.raises(ValueError, match="classification changed"):
        ci.finish(tmp_path, selected, tmp_path / "validation.json")
    assert len(recorded) == 1


@pytest.mark.parametrize("profile", ["full", "release"])
def test_merge_selects_authoritative_dispatch(merge_context, monkeypatch, profile):
    module, state = merge_context
    from repo_tools import release_changes as changes

    branch = "release-please--branches--main"
    policy = {"validation": {"full": sorted(state["required"]), "release": ["Release validation"]}}
    proof = {"run_id": 90, "run_attempt": 1}
    monkeypatch.setattr(ci, "policy_at", lambda *args: policy)
    monkeypatch.setattr(ci, "items", module.items)
    monkeypatch.setattr(ci, "release_changes", lambda *args: (True, "release"))
    monkeypatch.setattr(ci, "verified_base", lambda *args: proof)
    monkeypatch.setattr(ci, "branch_at", lambda *args: branch)
    monkeypatch.setattr(changes, "branch_at", lambda *args: branch)
    state["pr"]["head"]["ref"] = branch
    state["runs"][0].update(event="workflow_dispatch", head_branch=branch, run_attempt=1)
    state["runs"].append({**state["runs"][0], "id": 101, "event": "pull_request"})
    names = ["CI context", "CI result", *policy["validation"][profile]]
    state["jobs"] = [
        {"name": name, "status": "completed", "conclusion": "success"} for name in names
    ]
    state["evidence"].update(
        schema=2,
        profile=profile,
        run_attempt=1,
        base_sha=state["base"],
        base_verification=proof if profile == "release" else None,
    )
    assert cli.main(state["arguments"]) == 0
    state["runs"].append({**state["runs"][0], "id": 102, "conclusion": "failure"})
    assert cli.main(state["arguments"]) == 1


def test_schema2_record_uses_run_attempt_and_context(merge_context, monkeypatch, tmp_path):
    module, state = merge_context
    git = state["git"]
    git("checkout", "--detach", state["head"])
    event = tmp_path / "event.json"
    event.write_text("{}")
    for name, value in {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_SHA": state["head"],
    }.items():
        monkeypatch.setenv(name, value)
    selected = {
        "head_sha": state["head"],
        "checkout_sha": state["head"],
        "profile": "full",
        "base_sha": state["base"],
        "base_verification": None,
    }
    output = tmp_path / "validation.json"
    module.record(output, root=tmp_path, context=selected)
    evidence = json.loads(output.read_text())
    assert evidence["schema"] == 2
    assert evidence["run_attempt"] == 2
    assert evidence["tree_sha"] == state["tree"]
    assert all(evidence[key] == value for key, value in selected.items())
    selected["head_sha"] = "other"
    with pytest.raises(ValueError, match="context"):
        module.record(output, root=tmp_path, context=selected)


@pytest.mark.parametrize("change", ["missing", "duplicate", "overlap", "gate", "required"])
def test_profile_policy_is_validated(change):
    policy = checks.load_policy(root=Path(__file__).resolve().parents[3])
    if change == "missing":
        del policy["validation"]["release"]
    elif change == "duplicate":
        policy["validation"]["full"].append(policy["validation"]["full"][0])
    elif change == "overlap":
        policy["validation"]["release"] = policy["validation"]["full"][:1]
    elif change == "gate":
        policy["validation"]["full"].append("CI result")
    else:
        policy["protection"]["required_status_checks"]["checks"].append(
            {"context": "Extra", "app_id": 15368}
        )
    with pytest.raises(ValueError):
        checks.validate_policy(policy)


@pytest.mark.parametrize("profile", ["full", "release"])
def test_selected_jobs_fetch_one_collection(ci_state, monkeypatch, profile):
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ["CI context", "CI result", *POLICY["validation"][profile]]
    ]
    reads = []

    def items(endpoint, key=None):
        reads.append((endpoint, key))
        return jobs

    monkeypatch.setattr(ci, "items", items)
    monkeypatch.setattr(checks, "items", lambda *args: pytest.fail("duplicate job fetch"))
    ci.check_selected_jobs(REPOSITORY, 100, POLICY, profile, gate=True)
    assert reads == [
        (f"repos/{REPOSITORY}/actions/runs/100/jobs?filter=latest&per_page=100", "jobs")
    ]


@pytest.mark.parametrize("profile", ["full", "release"])
def test_context_and_result_summaries(ci_state, tmp_path, monkeypatch, profile):
    ci_state["eligible"] = profile == "release"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cli.main(["check-ci-context"]) == 0
    selected = ci.context(Path.cwd())
    assert f"Profile: <code>{profile}</code>" in summary.read_text()
    assert "Base commit: <code>base</code>" in summary.read_text()
    assert "Head commit: <code>head</code>" in summary.read_text()
    ci_state["jobs"] = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ["CI context", *POLICY["validation"][profile]]
    ]
    monkeypatch.setattr(checks, "record", lambda *args, **kw: None)
    monkeypatch.setenv("CI_CONTEXT", json.dumps(selected))
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.enterprise.invalid")
    assert cli.main(["check-ci-result"]) == 0
    output = summary.read_text()
    assert "Validation passed" in output
    assert "Performed validation" in output
    assert "https://github.enterprise.invalid/owner/project/actions/runs/100/attempts/1" in output
    assert "CI context" in output and "CI result" in output


def test_delegate_summary_uses_verified_profile(ci_state, tmp_path, monkeypatch):
    selected = ci.context(tmp_path)
    selected.update(role="delegate", profile="release", reason="wait for dispatch")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    ci.write_summary("CI context", selected)
    assert "Awaiting authoritative validation" in summary.read_text()
    assert "Profile: <code>release</code>" not in summary.read_text()
    evidence = {"schema": 2, "profile": "full", "run_attempt": 1, "base_sha": "base"}
    monkeypatch.setattr(checks, "check_evidence", lambda *args, **kw: evidence)
    monkeypatch.setenv("CI_CONTEXT", json.dumps(selected))
    assert cli.main(["check-ci-result"]) == 0
    output = summary.read_text()
    assert "Profile: <code>full</code>" in output
    assert "Reused" in output and "authoritative run 100, attempt 1" in output


@pytest.mark.parametrize("unwritable", [False, True])
@pytest.mark.parametrize("success", [False, True])
def test_summary_io_does_not_change_gate_result(
    ci_state, tmp_path, monkeypatch, success, unwritable
):
    selected = ci.context(tmp_path)
    selected["profile"] = "full"
    monkeypatch.setenv("CI_CONTEXT", json.dumps(selected))
    monkeypatch.setattr(checks, "record", lambda *args, **kw: None)
    if unwritable:
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path))
    else:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    if not success:
        ci_state["jobs"][-1]["conclusion"] = "failure"
    assert cli.main(["check-ci-result"]) == (0 if success else 1)


def test_failure_summary_escapes_diagnostics(ci_state, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    selected = ci.context(tmp_path)
    selected["reason"] = '<script>alert("x")</script>\n# Heading'
    monkeypatch.setenv("CI_CONTEXT", json.dumps(selected))
    assert cli.main(["check-ci-result"]) == 1
    output = summary.read_text()
    assert "Validation failed" in output
    assert "Release validation" in output
    assert "<script>" not in output
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; # Heading" in output
    ci.write_summary("CI result", error="<img src=x>\nexplanation")
    assert "&lt;img src=x&gt;\nexplanation" in summary.read_text()


def test_context_failure_summary(ci_state, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    ci_state["pr"]["state"] = "closed"
    assert cli.main(["check-ci-context"]) == 1
    assert "PR must be open" in summary.read_text()
    assert "Validation failed" in summary.read_text()


def test_local_classification_does_not_write_summary(tmp_path, monkeypatch, capsys):
    from repo_tools.commands import check_ci_context

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setattr(
        check_ci_context, "release_changes", lambda *args: (False, "source changed")
    )
    assert cli.main(["check-ci-context", "--classify", "--base", "base", "--head", "head"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "release_only": False,
        "reason": "source changed",
    }
    assert not (tmp_path / "summary").exists()
