# Dependency management

## Four different kinds of version

| Version source | Meaning |
| --- | --- |
| `version.txt` and component metadata | The shared release number of this repository's deliverables |
| A member's `[project].dependencies` | Compatible runtime dependency ranges advertised to consumers |
| Root dependency groups and `uv.lock` | Requested development tools and their resolved Python dependency versions |
| System tool installation | CMake, compilers, native analysis tools, Doxygen, and uv itself |

Changing a tool does not require setting its version to the repository release number. A requirement
such as `release-lab-core>=0.1.0` describes the oldest compatible API, not the current release.

## Workspace sharing and conflicts

All Python members share the root `uv.lock` and, by default, one `.venv`. The root's
`[tool.uv.sources]` maps sibling dependencies to workspace projects for development.
uv resolves the workspace together; selecting `uv run --package release-lab-package-a` does not create
a separate environment or allow incompatible versions of the same dependency to coexist there.
See [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/).

The `lint`, `test`, `dev`, `docs`, and `coverage` groups organize installation choices. They do not
isolate dependencies. uv resolves all groups for the shared lockfile, including groups that are not
currently installed. The default `dev` group includes lint and test tools plus the private `repo-tools`
package; documentation and coverage commands explicitly request their groups. A lockfile can contain alternative versions for
different Python versions or platforms, but one environment still needs a compatible selection.

For example, if one selected tool requires `shared-lib<2` and another requires `shared-lib>=2`,
there is no compatible environment. Locking/syncing fails rather than safely installing both
versions. Resolve that by:

1. Reading the resolver's dependency chain and finding compatible tool releases or valid ranges.
2. Upgrading or replacing the conflicting tool and validating the workflows it affects.
3. If the tool is an independent CLI, running it in an isolated uv tool environment with an explicit
   version. For example, `uv tool run --from "ruff==${RUFF_VERSION}" ruff --version` illustrates that mechanism
   after setting `RUFF_VERSION` to your chosen approved version;
   the repository's normal Ruff command remains `uv run ruff`.
4. If applications themselves require incompatible runtime libraries, moving the conflicting
   application into a separate project outside workspace membership, with its own environment and
   lockfile. Use an explicit process or service boundary when the applications must communicate.

An isolated CLI cannot assume it can import the editable workspace packages. Its environment is
also outside this repository's lockfile. uv describes those boundaries in its
[tool environment documentation](https://docs.astral.sh/uv/concepts/tools/).
This template does not declare mutually exclusive groups or workspace members. Avoid forcing an
incompatible resolution with overrides or manually installing conflicting packages into `.venv`.

The private maintenance package is an editable path dependency at `tools/repo_tools`, resolved
through the same root lockfile. It has no runtime dependencies and is outside workspace membership,
so `uv build --all-packages` builds only the product distributions. Its version does not follow
`version.txt`; see the [package guide](../tools/repo_tools/README.md).

## Where to declare dependencies

- Put runtime dependencies in the consuming component's `pyproject.toml`, even when another member
  already depends on the same library.
- Put shared Python development tools in the appropriate root dependency group.
- Put build-backend requirements in the component's `[build-system].requires`.
- Keep native/system tools outside Python dependencies; record their setup requirements
  in the [workstation guide](workstation.md).

Build backends such as setuptools run in isolated build environments. Their requirements are not
automatically pinned by the workspace's runtime lockfile. Likewise, an installed wheel uses its
published dependency metadata; the consumer does not inherit this repository's `uv.lock` or
workspace source mappings. See [uv's distribution build guidance](https://docs.astral.sh/uv/concepts/projects/build/).

## Repository build backend

The root `[tool.uv].build-constraint-dependencies` declares the setuptools pin. This separate
constraint pins the backend for editable installations through `uv sync`/`uv run`, local wheel
checks, and release builds. Each member and the private tooling package retain `setuptools>=77`
in their build requirements;
consumers rebuilding an individual source distribution do not inherit the root constraint.

The root also requires uv 0.10.9 or newer, the release that fixed workspace build-constraint handling.
See [uv 0.10.9 release notes](https://github.com/astral-sh/uv/releases/tag/0.10.9).
This pins the backend, not every input to a build or all third-party source-build dependencies.

To upgrade the backend, edit that one root constraint to the chosen tested version, then run:

```text
uv lock
uv sync --locked --all-packages --reinstall-package release-lab-core --reinstall-package release-lab-package-a --reinstall-package release-lab-package-b --reinstall-package release-lab-package-a-cli --reinstall-package monorepo-repo-tools
uv run repo-tools check-workspace
uv run repo-tools check-python
uv run pytest
uv run repo-tools check-python-install
```

Explicit reinstallation rebuilds existing editable packages with the new backend. Adapt the member
list after adding or renaming packages. Review the generated lockfile without requesting unrelated
upgrades, and inspect built wheels' `.dist-info/WHEEL` metadata to verify the `Generator` version.

## Add and inspect dependencies

Run these examples from the repository root, substituting the package you actually need:

```bash
uv add --package release-lab-package-a 'httpx>=0.28,<1'
uv add --group docs 'sphinx>=9.1,<10'
uv tree --package release-lab-package-a
uv tree --group docs --invert --package sphinx
```

For a new sibling dependency, add its distribution name to the consuming member's dependencies and
ensure the root has a matching `{ workspace = true }` source entry, then run `uv lock`.
New components also need the registrations listed in the [architecture guide](architecture.md#adding-a-python-package).
Commit the declaration changes and regenerated `uv.lock` together. Never hand-edit the lockfile.
The commands follow [uv's dependency management interface](https://docs.astral.sh/uv/concepts/projects/dependencies/).

## Upgrade and review

Upgrade a specific dependency within its declared range, inspect the result, and synchronize:

```bash
uv lock --upgrade-package sphinx
git diff -- pyproject.toml uv.lock
uv sync --locked --all-packages --group docs
```

To move outside an existing range, update the declaration using `uv add --group` or
`uv add --package` first. Use `uv lock --upgrade` only for an intentional broad refresh.
Review changed versions, transitive additions/removals, Python compatibility, and release notes;
mention the reason for the upgrade in the PR.

| Change | Validation |
| --- | --- |
| Runtime dependency or package metadata | pytest, Ruff, per-member type checks, isolated wheel checks |
| Ruff, ty, pytest, or other development tooling | The affected checks and the ordinary Python suite |
| Documentation dependencies or Doxygen | Complete documentation build with warnings as errors |
| Setuptools build constraint | Rebuild editable packages and distributions; run type, unit, and isolated wheel checks |
| Coverage dependencies | Python and native coverage command on Linux/GCC |
| Compiler, CMake, Ninja, or native analysis tool | Doctor, a fresh native build, CTest, install-consumer checks, and affected analysis/sanitizer/coverage workflows |

Keep isolated pre-commit hook revisions aligned when upgrading their corresponding workspace tools
(especially Ruff). The uv executable, hook revisions, GitHub Actions versions, and native tools are
not pinned by `uv.lock`; review their own configuration or installation source separately.
Use the existing [contribution commands](CONTRIBUTING.md) and [testing guide](testing.md).

Dependabot uses an explicit `chore` commit prefix with a dependency scope for uv, GitHub Actions,
and pre-commit updates. Subjects such as `chore(deps): bump dependency` and
`chore(deps-dev): update tools` satisfy the Conventional Commit policy without relying on inferred
repository style. Weekly schedules and update groups are configured in `.github/dependabot.yml`.

The actionlint version has one source: its official hook revision in the pre-commit configuration.
Python quality invokes that exact hook, and Dependabot's existing pre-commit updates cover upgrades.
After upgrading, run `uv run pre-commit run actionlint --all-files` and review any new diagnostics.

GitHub Actions are pinned to full upstream commit SHAs with version comments. Dependabot's existing
GitHub Actions group proposes updates. Review both the commit and its upstream release when
updating a pin; keep the comment aligned. No extra CI job is needed for this policy.
