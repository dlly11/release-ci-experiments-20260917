# Release CI Experiments

Public sample repository for release workflow experiments.

```text
core ──> package_a ──> package_a_cli
  └────> package_b
```


## Quick start

Install the prerequisites for your platform using the [workstation guide](docs/workstation.md).
From the repository root:

```bash
uv sync --locked --all-packages
uv run release-lab-package-a-cli "Ada Lovelace"
cmake --preset dev
cmake --build --preset dev
ctest --preset dev
./build/dev/native/apps/package_a_cli/release-lab-package-a-cli Ada
```

Native tests require a C++ compiler and CppUTest. See [offline native builds](docs/native-quality.md#cpputest-dependency-policy)
when dependencies must come from an approved local source.

## Repository layout

```text
.
├── python/
│   ├── packages/
│   │   ├── core/
│   │   ├── package_a/
│   │   └── package_b/
│   └── apps/
│       └── package_a_cli/
├── native/
│   ├── packages/
│   │   ├── core/
│   │   ├── package_a/
│   │   └── package_b/
│   └── apps/
│       └── package_a_cli/
├── cmake/                       # shared compiler and analysis policy
├── docs/                        # repository-wide documentation and Sphinx landing page
├── tools/                       # private repo-tools package and tool configuration
├── CMakeLists.txt               # native build graph
├── CMakePresets.json            # dev, analysis, sanitizer, and release builds
├── pyproject.toml               # uv workspace and shared Python policy
├── version.txt                  # canonical repository version
└── uv.lock                      # committed Python dependency lock
```

## Guides

- [Documentation site](https://dlly11.github.io/release-ci-experiments-20260917/): component examples and API references.
- [Contributing](docs/CONTRIBUTING.md): development workflow, commit policy, and pull requests.
- [Testing](docs/testing.md): local checks, coverage, and CI responsibilities.
- [Architecture](docs/architecture.md): component boundaries, new packages, and native consumption.
- [Dependencies](docs/dependencies.md): shared environments, conflicts, and tool upgrades.
- [GitHub setup](docs/github-setup.md): hosting, repository settings, and release credentials.
- [Releases](docs/releases.md): version metadata, automation, and recovery.
- [Adopting the template](docs/adopting.md): naming, registration, and initialization.
- [Security](docs/SECURITY.md): private vulnerability reporting.

## License

See [LICENSE](LICENSE) for this project's licensing terms.

Created from the [Python and C monorepo template](https://github.com/dlly11/python-c-monorepo-template), version 2.0.2.
