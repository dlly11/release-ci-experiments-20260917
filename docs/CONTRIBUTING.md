# Contributing

Keep changes within a component where possible and preserve the dependency directions documented
in `docs/architecture.md`.

Use the [workstation guide](workstation.md) for setup and diagnostics, the
[adoption guide](adopting.md) when changing template names or adding components, and the
[dependency guide](dependencies.md) when adding or upgrading libraries and tools.

Before opening a pull request, run the relevant [local validation commands](testing.md#local-validation).
The full Linux checklist runs pytest through coverage once. Other platforms can run Python tests
and native checks locally, with coverage enforced by Linux CI.

## Commit messages and pull requests

Use a Conventional Commit subject for every new commit and the PR title, for example
`feat(package-a): add JSON output`. Install both local hooks after synchronizing the workspace:

```bash
uv run pre-commit install
```

The message hook checks the first line, sharing the same policy as the
PR-title validator. Bodies and footers remain free-form. File checks run at the `pre-commit` stage.

Manual checks:

```bash
uv run repo-tools check-pr-title "feat(package-a): add JSON output"
COMMIT_MESSAGE_FILE=$(git rev-parse --git-path COMMIT_EDITMSG)
uv run repo-tools check-commits --message-file "${COMMIT_MESSAGE_FILE}"
git fetch origin
uv run repo-tools check-commits --base origin/main --head HEAD
```

`pre-commit run --all-files` runs file checks; it does not check a commit message. To exercise the
message hook directly, use the same resolved path:

```bash
COMMIT_MESSAGE_FILE=$(git rev-parse --git-path COMMIT_EDITMSG)
uv run pre-commit run conventional-commit --hook-stage commit-msg --commit-msg-filename "${COMMIT_MESSAGE_FILE}"
```

These shell examples use Bash (including Git Bash on Windows). Git resolves the correct path for
both ordinary clones and linked worktrees, where `.git` is a file. `COMMIT_EDITMSG` exists after a
commit attempt; before then, create a temporary text file containing your proposed subject and
pass its path instead. Quoting the path also supports directories containing spaces.

If a new commit is rejected, correct its subject and retry. For the latest existing commit, use
`git commit --amend -m "fix(core): handle empty input"`. For older commits on your PR branch, use
`git rebase -i origin/main` and mark the affected commits `reword`; resolve any `fixup!` or `squash!`
commits before submitting. Rebase onto `origin/main` when updating a branch. Default Git merge and
revert messages also fail the subject policy; supply a subject such as `revert: undo JSON output`.
After rewriting an already pushed branch, coordinate with anyone using it and push with
`git push --force-with-lease`.

The **Python quality** CI check validates the commits introduced by a PR even if local hooks were
skipped. The separate **Conventional PR title** check reruns on title edits without rerunning the
build matrix. GitHub supports three merge methods here:

| Method | Commits added to main |
| --- | --- |
| **Squash and merge** | One commit using the validated PR title |
| **Create a merge commit** | The original branch commits plus a merge commit using the validated PR title |
| **Rebase and merge** | Individual commits with their original messages and new SHAs |

Keep the validated title when confirming a squash or merge commit. Rebase does not create a
commit from the PR title or description. All methods reuse the PR's successful CI by verifying
that the final integrated contents match what was tested.

Put `!` in the PR title for breaking changes and in the relevant individual commit when preserving
commits. For a rebase, a breaking marker only in the PR title will not reach the commit history.
See [release behavior](releases.md#conventional-commits) for version and changelog effects.

Manual title workflow runs must select the open PR's current head branch in this repository and
its matching PR number. The workflow verifies the head repository, branch, and commit before
checking the live title. Ordinary PR events also validate fork PRs using their actual head commit.

The subject format is `type(scope)!: description`; scope and `!` are optional. Allowed types are
`build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, and `test`.
Types and scopes are lowercase. Scopes start with a letter or digit and can contain letters,
digits, `.`, `_`, `/`, and `-`. Descriptions must be nonempty with no surrounding whitespace or
control characters. This is the repository's subset of [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/),
implemented in `tools/repo_tools/src/repo_tools/conventional_commits.py`. See [CI event behavior](testing.md#pr-and-post-merge-responsibilities)
for checked commit ranges, and [releases](releases.md#conventional-commits) for version effects.


## Change requirements

Include tests for observable behaviour. Changes to public Python APIs, C headers, command-line
interfaces, or persistent formats require an explicit compatibility note in the pull request and
a breaking-change marker when compatibility cannot be preserved.

The Python check runs ty separately for each workspace member and then for the private tooling
package and its tests. Run the workspace consistency check after changing package names, membership, source
namespaces, or shared registrations; it reports missing, stale, and duplicate entries.

Git checks out text files with LF line endings through `.gitattributes`; `.editorconfig` configures
editors to preserve LF and the repository's formatting conventions. Binary files are automatically
detected and are not converted. Keep this policy when adding new text files on Windows.

The PR template provides short prompts for the change, validation, compatibility/dependencies, and
documentation. Use N/A for sections that do not apply.

Documentation is written in MyST Markdown. Keep package and application guidance within that
component's `docs` directory, keep overview, examples, and API reference in `docs/index.md`, and use standard fenced Mermaid
blocks so diagrams render both on GitHub and in Sphinx. The documentation build treats Sphinx and
Doxygen warnings as errors.
