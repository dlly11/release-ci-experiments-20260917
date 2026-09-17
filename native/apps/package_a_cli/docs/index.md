# Native package A CLI

The native `release-lab-package-a-cli` executable is the application boundary for package A. It accepts one
name, prints the generated greeting to standard output, and reports invalid usage or formatting
errors on standard error. The `--version` option reports the shared repository release version.

## Native package A CLI examples

Build the application and its dependencies:

```bash
cmake --preset dev
cmake --build --preset dev
```

Run it with exactly one name argument:

```console
$ ./build/dev/native/apps/package_a_cli/release-lab-package-a-cli Ada
Hello, Ada!
```

Quote names containing spaces:

```console
$ ./build/dev/native/apps/package_a_cli/release-lab-package-a-cli "Ada Lovelace"
Hello, Ada Lovelace!
```

Print the application version:

```console
$ ./build/dev/native/apps/package_a_cli/release-lab-package-a-cli --version
release-lab-package-a-cli X.Y.Z
```

`X.Y.Z` is the current value from `version.txt` and the generated CLI version header.

## Native package A CLI version API

The generated header `<release_lab/package_a_cli_version.h>` is installed with the native artifacts.

```{doxygendefine} RELEASE_LAB_PACKAGE_A_CLI_VERSION
:project: native
```

```{doxygendefine} RELEASE_LAB_PACKAGE_A_CLI_VERSION_MAJOR
:project: native
```

```{doxygendefine} RELEASE_LAB_PACKAGE_A_CLI_VERSION_MINOR
:project: native
```

```{doxygendefine} RELEASE_LAB_PACKAGE_A_CLI_VERSION_PATCH
:project: native
```
