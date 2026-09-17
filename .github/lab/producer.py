"""Create controlled sandbox events using the workflow's short-lived token."""

# Sandbox inputs are passed as argv; no shell or token is interpolated.
# ruff: noqa: S603, S607

import base64
import json
import os
import subprocess
import time


def api(path, method="GET", **fields):
    command = ["gh", "api", "--method", method, f"repos/{os.environ['GITHUB_REPOSITORY']}/{path}"]
    for key, value in fields.items():
        command.extend(["-f", f"{key}={value}"])
    return json.loads(subprocess.check_output(command, text=True))


case = os.environ["CASE"]
operation = os.environ["OPERATION"]
marker = os.environ["MARKER"]
branch = f"lab/{case}"
number = os.environ.get("PR_NUMBER", "")
if operation in {"create", "update"}:
    if operation == "create":
        base = api("git/ref/heads/probes")["object"]["sha"]
        api("git/refs", "POST", ref=f"refs/heads/{branch}", sha=base)
    current = api(f"contents/lab-probe.txt?ref={branch}")
    message = f"chore: probe {case} {operation}"
    if marker == "subject":
        message += " [skip ci]"
    elif marker == "body":
        message += "\n\n[skip ci]"
    elif marker == "trailer":
        message += "\n\n\nskip-checks: true"
    content = base64.b64encode(f"{case} {operation} {time.time_ns()}\n".encode()).decode()
    result = api(
        "contents/lab-probe.txt",
        "PUT",
        message=message,
        content=content,
        sha=current["sha"],
        branch=branch,
    )
    print(json.dumps({"commit": result["commit"]["sha"], "message": message}))
    if operation == "create":
        pr = api(
            "pulls",
            "POST",
            title=f"chore: probe {case}",
            head=branch,
            base="probes",
            body="Isolated trigger experiment; sample content only.",
        )
        number = pr["number"]
        print(json.dumps({"pr": number, "url": pr["html_url"]}))
    if os.environ["DISPATCH"] == "true":
        for workflow in ("ci.yml", "pr-title.yml"):
            subprocess.run(
                [
                    "gh",
                    "workflow",
                    "run",
                    workflow,
                    "--repo",
                    os.environ["GITHUB_REPOSITORY"],
                    "--ref",
                    branch,
                ],
                check=True,
            )
elif operation in {"close", "reopen"}:
    pr = api(f"pulls/{int(number)}", "PATCH", state="closed" if operation == "close" else "open")
    print(json.dumps({"pr": pr["number"], "state": pr["state"]}))
else:
    raise ValueError(operation)
