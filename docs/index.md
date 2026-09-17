# Release CI Experiments

This site documents the repository conventions, Python packages and applications, and native C
libraries and applications. Every component owns its guide and examples beside its source.

The Python and C examples intentionally use the same dependency graph so that workspace policy,
testing, versioning, and release automation can be compared without coupling the two toolchains.

```{toctree}
:maxdepth: 2
:caption: Repository guides

architecture
workstation
../tools/repo_tools/README
adopting
dependencies
testing
native-quality
github-setup
releases
CONTRIBUTING
SECURITY
```

```{toctree}
:maxdepth: 2
:caption: Python components

../python/packages/core/docs/index
../python/packages/package_a/docs/index
../python/packages/package_b/docs/index
../python/apps/package_a_cli/docs/index
```

```{toctree}
:maxdepth: 2
:caption: Native C components

../native/packages/core/docs/index
../native/packages/package_a/docs/index
../native/packages/package_b/docs/index
../native/apps/package_a_cli/docs/index
```
