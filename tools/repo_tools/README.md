# Private repository tooling

This standard `src`-layout package contains the repository's maintenance commands and their tests.
It has no runtime dependencies. It is an editable development dependency, not a released workspace
component; its private version is independent of the product version.

From the repository root:

```bash
uv sync --locked --all-packages
uv run repo-tools --help
uv run repo-tools check-versions
uv run repo-tools doctor --profile python
uv run repo-tools check-github-settings --extended
```

## Checkout and Python environment

The installed CLI and `python -m repo_tools` discover a checkout from the current directory.
To select another checkout, put `--project-root PATH` before the command:

```bash
uv run repo-tools --project-root ../another-checkout check-versions
```

`--project-root` selects files and Git history; it does not switch or synchronize Python environments.
Metadata and artifact checks can operate on another checkout directly. Documentation and coverage
require that checkout's editable first-party packages and the relevant dependency group. Their
preflight checks import locations without importing project code and fail before changing output
if sources are missing or belong to another checkout. Custom virtual environments work when their
imports resolve to the selected checkout's sources; setting `PYTHONPATH` does not bypass the check.

For documentation, change into the target checkout and run:

```bash
uv sync --locked --all-packages --group docs
uv run --no-sync repo-tools build-docs
```

For coverage, use `--group coverage` and `check-coverage` instead. These commands use the same
Python interpreter for preflight and execution; system tools such as CMake still come from PATH.

## Before installation

Before installing dependencies, CI and workstation diagnostics use the one source launcher:

```bash
python tools/repo_tools/run.py doctor --profile all
python tools/repo_tools/run.py check-versions
```

The launcher defaults to its containing checkout. Its explicit `--project-root` option can target
another checkout, including an old release. Help and standalone message checks need no checkout.
Relative file arguments are relative to the working directory, regardless of the selected root.

## Adding a command

1. Add a module under `src/repo_tools/commands` with `add_arguments(parser)` and
   `execute(args, *, root)`, then register its hyphenated name in `cli.COMMANDS`.
2. Let the central CLI parse arguments and resolve the checkout. Pass the supplied root to helpers
   and subprocesses instead of rediscovering it or changing the process working directory. Declare
   genuinely checkout-independent behavior in the dispatcher, following the standalone checks.
3. Use argparse argument types for value validation and `args.parser.error(...)` for usage errors
   discovered during execution. Return the command's documented status for operational failures.
4. Add focused behavior tests under `tests`, using direct imports, explicit arguments, temporary
   roots, and the shared isolated `git` fixture. Test CLI behavior through `repo_tools.cli.main`;
   keep parsing separate from helper tests. The normal repository pytest run discovers these tests.
5. Keep package imports standard-library-only so the source launcher, help, and metadata checks
   work before dependencies are installed. Commands that require development tools must check
   prerequisites before changing outputs; follow the shared environment preflight when importing
   checkout packages.

The central CLI is the only command entry point; command modules do not need their own `main()`.
Package-level modules contain shared helpers. Update the relevant workflow guide when adding a
user-facing operation; CLI help remains the reference for command options.

`check-release-automation` is the workflow's read-only validator for explicit release credentials
and the managed PR/head eligible for auto-merge. It never merges a PR or changes GitHub settings;
the release workflow owns those writes. See the release guide for configuration and activation.

`check-ci-context` selects the workflow role and validation profile. Its local `--classify --base
SHA --head SHA` mode explains whether a committed change is metadata-only, without GitHub access.
`check-ci-result` requires successful jobs or matching authoritative dispatch evidence and records
schema-2 validation. Both use read-only GitHub access; see the testing guide for the trust rules.

See the [workstation guide](../../docs/workstation.md), [testing guide](../../docs/testing.md), and
[release guide](../../docs/releases.md) for workflows.
