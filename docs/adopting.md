# Project setup

This project was generated from a saved `template-config.toml`. That file records the
initial creation inputs and template identity; it does not synchronize subsequent edits.

## Develop locally

Follow [workstation setup](workstation.md), then run:

```bash
uv sync --locked --all-packages
uv run repo-tools check-workspace
uv run repo-tools check-versions
```

Run the [validation checklist](testing.md#local-validation) before the first push.
The generated configuration does not install compilers or development dependencies.

## Initialize GitHub

1. Initialize a local Git repository with `git init --initial-branch=main`.
2. Review all files, then create a Conventional Commit such as `chore: initialize project`.
3. Create an empty GitHub repository at `dlly11/release-ci-experiments-20260917` and push
   the initial `main` branch. Do not initialize the remote with a separate README or license.
4. Enable Actions and configure documentation hosting for <https://dlly11.github.io/release-ci-experiments-20260917/>.
   Follow the [hosting choices](github-setup.md#documentation-hosting) for default Pages,
   a Pages custom domain, or an external host. Setting the URL does not configure hosting.
5. Let initialization CI pass. If no run is created, dispatch `ci.yml` on `main`.
6. Configure the merge methods, required checks, release permissions, and branch protection
   in the [GitHub setup guide](github-setup.md#repository-settings). Confirm CODEOWNERS entries
   have access to the repository; syntax validation cannot check GitHub permissions.
7. Run `uv run repo-tools check-github-settings --repo dlly11/release-ci-experiments-20260917`.
8. Make subsequent changes on a branch and open the first protected PR. Its verified merge
   establishes normal release automation. Initialization itself does not authorize a release.

The generator creates local files only. It does not create commits, remotes, tags,
or GitHub settings.

For new components, follow the [architecture guide](architecture.md).
