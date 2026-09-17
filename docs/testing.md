# Testing and coverage

The repository runs tests at component boundaries and enforces coverage across production Python
and native C source. Compatibility tests, static analysis, sanitizers, and coverage remain
separate CI responsibilities so each failure identifies one kind of problem.

## Local validation

Run from the repository root after [workstation setup](workstation.md). This full checklist assumes
Linux/GCC. Coverage runs the Python and native tests; a separate pytest invocation is unnecessary.

```bash
uv run pre-commit run --all-files
uv sync --locked --all-packages --group coverage --group docs
uv run --no-sync repo-tools check-versions
uv run --no-sync repo-tools check-python-install
uv run --no-sync repo-tools check-coverage
uv run --no-sync repo-tools build-docs
cmake --preset analysis
cmake --build --preset analysis
cmake --build --preset analysis --target format-c-check
cmake --preset asan
cmake --build --preset asan
ctest --preset asan
```

On macOS or Windows, replace the coverage command with `uv run pytest --no-cov` and the `dev`
configure/build/CTest presets. The sanitizer preset is unavailable on Windows. For native changes,
also exercise the [installed consumer](architecture.md#consuming-a-native-installation).

For a focused Python change, use `uv run pytest --no-cov PATH_TO_TESTS` during development. Build
documentation with `uv run --group docs repo-tools build-docs` and open
`build/docs/html/index.html`; Sphinx and Doxygen warnings fail the build.

## PR and post-merge responsibilities

| Event | Quality work | Commit subjects | Release eligibility |
| --- | --- | --- | --- |
| Ordinary pull request | Full suite, CI result, and separate title check | PR head commits outside the event's base SHA | Tested evidence for the later merge |
| Manual CI (ordinary branch or main) | Full suite and CI result | Commits outside `origin/main` (none on main) | Explicit recovery only on current main |
| Managed release PR dispatch | Release validation when eligible; otherwise full suite | Commits outside the live base SHA | Authoritative evidence for the exact synchronized head |
| Managed release PR event | CI result verifies the authoritative dispatch; separate title check | Validated by the dispatch | No duplicate quality suite |
| Ordinary main push | Merged PR verification and version check | New squash/merge subjects and preserved or rebased PR commits | Latest successful verified push on current main |
| Initial branch creation (zero previous SHA) | Full suite; no validation record | Inherited history is the baseline and is skipped | Never |

Python 3.12 runs in **Coverage** on Linux/GCC; compatibility jobs cover 3.13 and 3.14 with
`--no-cov` to avoid collecting the same coverage on every interpreter. Required check names live
in `tools/github/repository-policy.json`. Pages builds/deploys independently on main. Release
builds and smoke-tests tagged artifacts without repeating the PR test and analysis suite.

Push CI on `main` runs only `Merged PR verification`. It walks the new first-parent history backward
from the push head, accepting squash commits, two-parent merge commits, and rebased PR sequences.
For each integration it checks the subjects, finds its merged GitHub PR, verifies that the original head
has a successful CI run with every job in the recorded profile completed successfully, and compares the merged
Git tree with the recorded tested tree. A merge commit must have the PR head as its second parent;
the verifier also checks subjects of the preserved PR commits newly introduced to main. Intermediate
PR commits do not need their own validation records: CI certifies the final integrated contents.

For a rebase, GitHub's `merge_commit_sha` identifies the final rewritten commit. The verifier groups
the contiguous preceding commits using GitHub's [commit-to-PR associations](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit),
validates each subject, and compares only the final tree with the PR record. Every new first-parent
commit must be accounted for, and push boundaries must contain complete PR integrations. Missing
or ambiguous associations within the push fail verification; no commit is skipped merely because
the final contents match. Original and rewritten commit counts or SHAs need not match to reuse CI.

Skipped checks are not accepted as passing. Version metadata is checked without installing tools
or rebuilding packages. The other CI jobs appear skipped on push runs because they already ran
on the PR.

The **CI result** job uploads a small `pr-validation` JSON record only after its selected suite
passes. Schema 2 binds the repository, run ID and attempt, original head, actual checkout and Git
tree, profile, and base SHA. Reduced validation also records the successful main verification run
and attempt. The record certifies tracked contents; release distributions are built from their tag.
Automatic release-PR runs consume the dispatch's record and do not upload a second one.

Post-merge verification independently checks the profile and its jobs. Release-only evidence must
match the actual integration predecessor, an unchanged verified base run, and a fresh semantic
classification of the integrated changes. Legacy schema-1 records are accepted only for historical
full-suite commits, using the policy committed in that tested tree. New workflows require schema 2.

### Release-only validation

The reduced profile requires an open, same-repository Release Please PR targeting main, the
configured managed branch, a pending-release label, a conventional release title, and an unchanged
base with successful **Merged PR verification**. Its committed changes must be exactly:

- One increasing version, synchronized across `version.txt`, root/product `project.version`,
  the literal CMake project version, and the single-root release manifest.
- Only workspace version updates in `uv.lock`; dependencies, sources, hashes, and other fields
  must remain identical.
- A new changelog entry prepended without changing existing history.

The classifier reads the base revision's workspace metadata and runs the base revision's classifier
code. Changes to code, workflows, dependencies, configuration, file paths/modes, or unrelated
metadata fall back to full CI. An unsupported release layout or unavailable successful base
verification also uses full CI. API failures and stale PR identities fail rather than silently pass.
The PR introducing this mechanism uses full CI because its base does not yet support it.

**Release validation** runs on Linux/Python 3.12: commit subjects, locked workspace sync, workspace
and version checks, wheel/source builds and installed-wheel smoke checks, plus a native Release
build/install and downstream CMake consumer. The upstream template also checks its inventory and
runs a source-based creator generation smoke test. It omits compatibility/platform matrices,
coverage, docs, analysis, sanitizers, and frozen creator builds; those inputs are unchanged from the
verified base. Tagged release jobs still build and smoke-test the actual published artifacts.

In every credential mode, Release dispatches CI after lockfile synchronization with the PR number
and exact expected head. Automatic PR runs delegate to the newest matching dispatch and wait up to
35 minutes. A missing dispatch times out; a failed/cancelled run, changed head/base, or newer attempt
fails the gate. Retry release preparation to dispatch a fresh synchronized run. Event-specific
concurrency prevents a delegate from cancelling the dispatch. The cheap live title check remains
independent, including title edits.

The verifier reads records from the selected CI run only, fails on missing or expired evidence,
and never executes downloaded content. GitHub's repository artifact retention applies. See
[CI evidence recovery](releases.md#recovering-expired-ci-evidence) for retry limits, rerunning
original validation, and authorizing recovery from fresh CI on current main.

The **CI context** and **CI result** job summaries show the selected role/profile, selection reason,
and base/head commits. Delegates initially show that authoritative validation is pending; after
verification, their result summary reports the actual profile and links to the authoritative run
and attempt. Failures remain failures even if the informational summary cannot be written.

The post-merge job needs contents, actions, and pull-request read permissions.

## Python distribution checks

The Python quality job builds wheels and source distributions, then checks every wheel in a separate
temporary environment. Run the same check locally:

```bash
uv run repo-tools check-python-install
```

The command uses a fresh artifact directory and checks distribution names and versions before
installing. Each environment receives only its target wheel and declared dependencies. Local wheel
constraints ensure sibling dependencies come from this build without installing unrelated members.
Third-party runtime dependencies use the installer's configured indexes. The four example
components have none.
Build backends still need an available index or cache, as with `uv build`.
Installation runs from the selected project root so uv discovers its index configuration. Pass
credentials through uv's supported environment settings; the wheel environment is still explicitly
selected and separate from the workspace.

Checks run outside the checkout with isolated Python imports and no inherited `PYTHONPATH` or user
site-packages. They verify installed versions, module locations, `py.typed`, dependency consistency,
public API examples, and the installed CLI's normal, custom-prefix, and invalid-input behavior.
API/CLI checks time out after ten seconds; uv build/install commands after five minutes.
Failures report the package and command output and return a nonzero exit status. Temporary build
artifacts and environments are removed on both success and failure.

The same command separately builds and installs the private `repo-tools` package. Its smoke checks
verify console and module help outside the checkout and a version check against an explicit target.
The tooling wheel uses its own version and artifact directory.

Add a `SMOKE_CHECKS` entry in
[python_smoke_checks.py](../tools/repo_tools/src/repo_tools/python_smoke_checks.py) when introducing
a product distribution. Each `SmokeCheck` holds its import namespace, API example, and optional
`SmokeCommand` cases for installed executables. Command cases specify the executable name without
a platform suffix, arguments, and expected exit status/output. Keep CLI expectations in that entry when renaming
or adding an application; the installer runs those cases from the isolated environment rather
than matching product names. These checks cover the exercised install/API paths; ordinary
component tests remain responsible for deeper behavior.
CI runs the wheel checks once in Python quality or Release validation, alongside the separate Python
version test matrix. The release workflow continues to build the same distribution formats.

To smoke-test already-built release wheels without rebuilding them, run
`uv run repo-tools check-python-install --dist dist`. Release CI uses this mode before
uploading the exact wheels it checked. This mode checks product artifacts only and does not build
or install private tooling. Put `--project-root CHECKOUT` before `check-python-install` to select
version metadata and build/index configuration from another checkout; see
[asset recovery](releases.md#recovering-missing-release-assets). This validates the published artifacts
while the full unit-test and analysis suite remains on PRs.

## Native unit tests

CTest remains the native test orchestrator. The core, package A, and package B test executables use
CppUTest as their unit-test harness, while the package A CLI uses process-level CTest checks for
output and exit behaviour. Existing CTest names remain stable for filtering and CI diagnostics.

CppUTest is written in C++, so test-enabled native builds require a C++17 compiler. Public C headers
provide `extern "C"` guards for both the test harness and downstream C++ consumers. The dependency
is fetched only when `BUILD_TESTING=ON` and is excluded from installation and release archives.

CLI process tests check exit status, standard output, and standard error independently, including
empty input. Linux additionally checks that greeting and version output fail when redirected to
`/dev/full`. UBSan findings are fatal in sanitizer builds.

Each first-party native CTest test, including the installed consumer, has a 60-second execution
limit. The CLI output-comparison helper additionally stops its child process after ten seconds
and reports the executable and limit. These limits apply to local builds and CI.

## Private tooling tests

The normal `uv run pytest` command discovers `tools/repo_tools/tests`, covering:

- GitHub policy, commit/title validation, all three merge methods, CI evidence, and release recovery.
- Workspace registrations, product version consistency, and version-update rollback.
- Installed artifacts, checkout selection, isolated Python environments, and prerequisite failures.

Tests use temporary files, real local Git repositories and virtual environments, and mocked GitHub
API reads. They do not access the network or change committed metadata. The wheel-isolation
regression uses uv offline to verify that undeclared imports fail even with source on `PYTHONPATH`;
it skips when uv is unavailable. Normal development and CI provide uv.

Private tooling is linted, type-checked, and tested in the existing jobs; coverage thresholds
measure product code. Live GitHub settings audits are manual and read-only; see the
[release guide](releases.md).

## Coverage policy

| Stack | Measured scope | Required coverage |
| --- | --- | --- |
| Python | The four import packages, with branch measurement enabled | 90% aggregate |
| Native C | Source below `native/*/*/src`; C++ tests and generated files are excluded | 90% lines and 80% branches |

Python uses coverage.py through pytest-cov. Native coverage uses GCC/G++ instrumentation, gcov, and
gcovr. The native coverage preset is intentionally Linux and GCC only; the normal native matrix
uses GCC on Linux, Clang on macOS, and GCC/MinGW on Windows. MSVC has compiler-option support in
CMake but is not verified by the current CI matrix.

Coverage gates must not be reduced merely to make a change pass. Add tests for observable
behaviour, or make a separately reviewed policy change when the existing threshold is no longer
appropriate.

## Run coverage locally

Install Python 3.12, uv, CMake, Ninja, GCC, and gcov, then run:

```bash
uv sync --locked --all-packages --group coverage
uv run --group coverage repo-tools check-coverage
```

For an approved local CppUTest tree, add `--cpputest-source PATH`; see the
[offline native setup](native-quality.md#cpputest-dependency-policy). Preconfiguring a CMake cache
with a local source is insufficient because coverage cleans its build directory before each run.

Coverage rejects platforms other than Linux before probing dependencies or changing outputs.
Documentation and coverage check that the selected checkout's first-party packages and required
Python tools are available through the running interpreter, including documentation extensions
and the theme. They run Python tools as isolated modules, so another `pytest`, `gcovr`, or `sphinx`
executable on PATH cannot select a different environment. Coverage also checks its native executables.

These prerequisite failures leave existing reports unchanged. Follow the reported sync and rerun
commands; previous reports still describe their original run. A later build or test failure can
leave partial output. `--project-root` selects checkout files, not a Python environment; see the
[package guide](../tools/repo_tools/README.md#checkout-and-python-environment).

After preflight succeeds, the command removes the previous `build/coverage` directory, runs both
test suites, enforces their thresholds, and writes reports beneath `build/coverage/reports`:

- `summary.md` contains the combined line and branch totals.
- `python/html/index.html` and `native/index.html` are browsable annotated reports.
- Each stack also produces JSON or Cobertura XML for automation.

To work only with the instrumented native build, use the standard presets followed by gcovr:

```bash
cmake --preset coverage
cmake --build --preset coverage
ctest --preset coverage
uv run --group coverage gcovr --config tools/coverage/gcovr.cfg \
  --object-directory build/coverage/native
```

## Continuous integration reports

The `Coverage` job writes its table to the GitHub Actions job summary and retains the complete
report directory as the `coverage-reports` artifact for 14 days. Reports are uploaded even when a
test or threshold fails, when enough data was generated to create them. See
[CI responsibilities](#pr-and-post-merge-responsibilities) for interpreter assignments.

## Native release smoke checks

`python tools/repo_tools/run.py check-native-install PREFIX` validates the version headers and runs the exact
installed CLI for `--version` and a greeting. Missing executables, nonzero exits, unexpected output,
and ten-second execution timeouts fail the check. The command must run on the target platform.

Both PR native jobs and release publishing also build the existing C++ consumer against the
Release installation and run its CTest check. Pass `-DMONOREPO_INSTALL_PREFIX=ABSOLUTE_PREFIX` when
configuring the consumer; package discovery is restricted to that installation. This catches missing
libraries, broken exports, and link/runtime failures without repeating the full unit-test suite in
release jobs. Failed checks prevent packaging and upload.

## Workflow linting

The Python quality job runs `uv run pre-commit run actionlint --all-files`. Local commits use the
same actionlint hook for changed workflow files. Its version is pinned in the pre-commit config;
optional ShellCheck and Pyflakes integrations are disabled so installed optional tools do not
change the result. No separate workflow-lint job is required.

