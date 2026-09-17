# Repository tooling and configuration

This directory contains the private maintenance package and shared tool configuration.

- [repo_tools/](repo_tools/README.md) provides the `repo-tools` CLI, its source launcher, and tests.
- `release-please/` contains Release Please's policy and version-state manifest. The release
  workflow passes both paths explicitly.
- `sphinx/` configures the repository-wide MyST, Mermaid, autodoc, and Breathe documentation site.
- `doxygen/` configures XML generation for the public native C headers consumed by Breathe.
- `github/repository-policy.json` defines managed repository settings, required check names, and validation profiles.
  The read-only audit and CI evidence checks share this policy.
- `coverage/` defines gcovr source filtering and the native line and branch thresholds.

Configuration based on conventional discovery remains at the repository root. In particular,
Clang tooling, EditorConfig, Git, pre-commit, uv, and CMake integrations expect their standard
filenames in the project or a parent directory. Keeping those entry points at the root lets CLIs,
editors, and language servers work without repository-specific flags.

## Adding components

Component additions are described in [architecture](../docs/architecture.md#adding-a-python-package).
Type/version checks discover members automatically; release, coverage, smoke, and documentation
policy still require explicit registration.
