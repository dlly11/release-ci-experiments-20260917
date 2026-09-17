# GitHub setup

Configure these settings after creating the remote repository. The creator writes local files;
it does not configure GitHub or documentation hosting. For version policy, the release sequence,
and recovery, see the [release guide](releases.md).

## Documentation hosting

The creation recipe's `github.docs_url` sets published links and Sphinx metadata. It does not
provision a site, configure DNS, or choose a deployment service. Choose the matching setup:

| Hosting choice | Required setup |
| --- | --- |
| Default GitHub Pages | Enable Pages with **GitHub Actions** as its source. Keep the included documentation deployment workflow and use `https://OWNER.github.io/REPOSITORY/`. |
| Custom domain on GitHub Pages | Enable Pages with **GitHub Actions** as its source, configure the custom domain in Pages settings, and configure DNS with your provider. Use the site's HTTPS URL in the recipe. |
| External documentation host | Configure that host to build and publish the Sphinx site, or deploy `build/docs/html` to it. Adapt or disable `.github/workflows/docs.yml` so it does not attempt a Pages deployment you do not use. Keep the PR documentation build for validation. |

For a Pages custom domain, follow GitHub's [domain and DNS setup guide](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).
This repository deploys through Actions; a `CNAME` file is not required and does not configure
that deployment's domain. Configuring a URL alone does not make it reachable.

## Repository settings

These settings live in GitHub, outside the checked-in workflows. Configure them in every
repository created from this template before relying on enforcement or unattended releases:

1. Under **Settings > Actions > General**, allow GitHub Actions to create pull requests.
2. Protect `main`, require pull requests and passing CI checks, and apply the rules to
   administrators. Require **CI result** and **Conventional PR title**, with GitHub Actions as
   their expected source. CI result requires every job in the selected validation profile to
   actually succeed. Keep branches up to date before merging and disallow force pushes and branch
   deletion. Zero required approvals supports a solo maintainer; teams can add review requirements.
   Do not require individual quality jobs: release-only PRs intentionally skip the full suite.
   **Merged PR verification** runs after merging and must not be a required PR check.
3. Under **Settings > General > Pull Requests**, enable **Allow squash merging**, **Allow merge
   commits**, and **Allow rebase merging**. Use the **pull request title** for squash and merge title
   defaults (`squash_merge_commit_title: PR_TITLE`, `merge_commit_title: PR_TITLE`), including
   single-commit squash PRs. Use commit messages for squash bodies and the PR description for
   merge bodies (`squash_merge_commit_message: COMMIT_MESSAGES`, `merge_commit_message: PR_BODY`).
   Turn off **Require linear history** on `main` to permit merge commits. Keep the validated
   subject when confirming squash or merge commits; the UI still permits editing that default,
   and the push check detects invalid subjects after merging.
4. Restrict release tag creation to maintainers and the release workflow. Run both workflows on
   a PR before selecting their required check names. The title check belongs to `pr-title.yml`;
   renaming jobs later requires updating the protection settings.

### Migrating existing required checks

First open an ordinary PR containing this workflow update and let the full suite, **CI result**,
and **Conventional PR title** pass. Keep existing branch protection until this has succeeded.
Then replace the individual required quality checks with CI result and Conventional PR title,
keeping strict branch updates, the GitHub Actions source, and administrator enforcement.
Merge the update and run the [settings audit](#audit-the-managed-github-settings). Confirm a release
PR uses one authoritative suite and that its merge passes **Merged PR verification** before
relying on unattended releases. Repository settings are external; changing the policy file does
not apply them. Recovery CI on main always runs the full suite.

By default, the workflow uses its short-lived `GITHUB_TOKEN` with explicit permissions.
Token-created or updated PRs produce approval-required workflow runs; other token-generated
events, including pushes, do not start workflows. Explicit `workflow_dispatch` calls do start
workflows, so Release dispatches CI and title validation after synchronizing its branch.
The dispatched run performs the authoritative validation without approval. GitHub may still
require the automatic PR runs before its required checks allow merging. Those CI runs verify
the dispatched result instead of repeating the quality suite. See
[GitHub's token event behavior](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs).
The title workflow uses only read access to contents and pull requests. No additional credential
is required for this default mode. Manual dispatch requires the workflow on the default branch.

### Approving and retrying release PR checks

1. Wait for **Prepare release PR** to synchronize the lockfile and dispatch validation for the
   final head. An earlier run may have been superseded by that commit.
2. If the PR shows **Approve workflows to run**, a maintainer with write access should approve
   the current runs. A successful dispatch alone does not guarantee GitHub will consider the
   required PR checks satisfied.
3. If validation fails, inspect its logs and fix the cause. Retry the authoritative dispatch for
   the current head before retrying a failed delegating PR run. Use the
   [evidence recovery guide](releases.md#recovering-expired-ci-evidence) for expired evidence.
4. Merge only when GitHub's required checks and any required reviews pass. For an expired
   approval run that cannot be retried, close and reopen the PR as a maintainer to request fresh
   PR checks; verify they use the synchronized head.

Approval-required runs can remain in Actions history or expire into failures. This is a
limitation of the default token mode, not a reason to bypass required checks. The template does
not delete workflow history automatically or use commit skip instructions to hide these runs.

## Optional unattended releases

Keep the defaults when enterprise policy prohibits additional automation credentials, and allow
for the approval step above. Where permitted, prefer an enterprise-approved GitHub App to remove
token-specific PR approval and optionally merge releases automatically. PAT mode remains available
for repositories whose policy permits it. Configure the chosen mode under
**Settings > Secrets and variables > Actions**:

| Name | Kind | Value |
| --- | --- | --- |
| `RELEASE_AUTH_MODE` | Variable | `github-token` (default), `app`, or `pat` |
| `RELEASE_AUTO_MERGE` | Variable | `false` (default) or `true` |
| `RELEASE_APP_CLIENT_ID` | Variable | Installed App's client ID; required for `app` |
| `RELEASE_APP_PRIVATE_KEY` | Secret | App private key; required for `app` |
| `RELEASE_PAT` | Secret | Approved repository-scoped token; required for `pat` |

For an App, install it on this repository with **Contents**, **Pull requests**, and **Issues**
read/write permissions. The workflow uses the official, SHA-pinned
[App token action](https://github.com/actions/create-github-app-token), scopes its token to this
repository, and creates and revokes a separate token within each release job that needs it.
Registration supplies an automation identity; no hosted application code or server is required.
An existing approved App can be used.
For PAT mode, prefer a fine-grained token with those same permissions on this repository and an
account allowed to perform the required operations. Follow enterprise approval and expiry policy;
rotate or renew it before expiry. Never put either credential in a creation recipe.

App/PAT mode uses the selected identity for Release Please, lockfile pushes, and auto-merge requests.
PR events start without the default token's approval requirement, but their CI delegates to the
authoritative dispatch sent after lockfile synchronization. A later lockfile commit supersedes
the initial head. Dispatch and PR concurrency are separate. Title checks remain independent.
Artifact jobs continue to use their own `GITHUB_TOKEN`.

Before setting `RELEASE_AUTO_MERGE=true`:

1. Configure App or PAT mode and all required credentials. Unset or unused secrets do not select
   an identity automatically; invalid selected configuration fails before release writes.
2. Enable **Allow auto-merge** in repository settings and ensure squash merging is enabled.
3. Confirm all intended required checks, strict branch updates, and administrator enforcement.
   Run the settings audit below; CI result enforces the full or release profile.
4. Keep review requirements appropriate for your team. Auto-merge waits for them; it does not
   approve PRs, bypass protection, or remove deployment approvals.

Only the open, same-repository Release Please PR targeting `main`, on the branch derived from
`tools/release-please/config.json`, with the pending-release label and synchronized head is eligible.
For a configured component/package name this is
`release-please--branches--main--components--NAME`; without one it is
`release-please--branches--main`. A renamed generated project uses its own configured name.
The automation supports the template's single-root simple strategy; custom/multi-package layouts
need an explicit automation adaptation before enabling auto-merge.
GitHub performs a squash merge using its conventional release title. Major releases are included;
ordinary PRs are unaffected. A head change between validation and the merge request rejects that
request. The resulting main push must still pass merged-PR verification before publishing assets.
Keep the default release branch/title convention when using this feature. Merge queues are outside
the current CI design; rulesets requiring them need a separate CI integration.

Missing or expired credentials, disabled repository auto-merge, and permission failures are shown
in the relevant release job. Correct the setup and retry release preparation after main's verified CI
passes. There is no fallback to another credential and no administrator merge bypass.

To stop future automatic merge requests, set `RELEASE_AUTO_MERGE=false`. To cancel an already
queued request, also run `gh pr merge PR_NUMBER --disable-auto` (or disable it in the PR UI).
Changing the variable alone does not cancel existing requests. To return fully to the default
token path, also set `RELEASE_AUTH_MODE=github-token`. Test activation through a complete release:
final PR checks, automatic merge, main verification, release creation, and asset publication.

## Audit the managed GitHub settings

`tools/github/repository-policy.json` records the intended default branch, merge defaults, PR
requirements, required checks and GitHub Actions source IDs, administrator enforcement, and
linear-history/force-push/deletion settings. It preserves the current solo-maintainer policy with
zero required approvals and permits squash, merge, and rebase integrations.

With an authenticated GitHub CLI, run the read-only audit manually:

```bash
uv run repo-tools check-github-settings
# Or target a repository explicitly, including a newly adopted template:
uv run repo-tools check-github-settings --repo OWNER/REPO
```

Without `--repo`, the command uses `gh repo view` to detect the checkout's repository. Reading
branch protection requires repository administration read access; a fine-grained token needs
**Administration: read**. The audit requires no write permissions and makes only GET API requests.
Exit status `0` means the managed settings match, `1` means settings differ, and `2` means the audit
could not complete because of policy, authentication, or API errors. Every difference includes the
expected and actual values. An inaccessible protection endpoint is an audit error, not evidence
that protection is absent.

The audit compares managed settings exactly, including the unordered set of required check names
and their application IDs. Additional required checks are reported too; unrelated GitHub settings
are ignored. Correct unintended differences in GitHub Settings, or edit the policy in a reviewed
PR for an intentional change, then rerun the audit. Adopters should also update the workflows when
changing branch or check names. The audit is not a CI job and never applies settings.

This policy covers classic branch protection and repository merge settings on GitHub.com. It does
not audit release tag restrictions, Pages, Actions workflow permissions, or organization rulesets.
Those remain separate setup responsibilities described above.

For additional read-only setup diagnostics:

```bash
uv run repo-tools check-github-settings --extended --repo OWNER/REPO
```

Extended mode lists active rules applying to the default branch and their sources, Actions workflow
permissions, repository auto-merge availability, and GitHub-reported CODEOWNERS errors. Rulesets
and capability settings are informational, not a replacement for the classic policy comparison.
The branch-rules API includes active inherited rules, but not disabled or evaluation-only rules.
See [GitHub's effective branch rules API](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch).

The audit completes independent reads even if another endpoint is inaccessible. Exit `1` also
includes CODEOWNERS errors; exit `2` means at least one requested check could not complete and takes
precedence over detected drift. A successful exit certifies the comparisons and reads described
here, not full enterprise-policy compliance. An unavailable classic protection endpoint remains
unassessed even when rulesets are visible. No settings are changed and this is not a CI job.
