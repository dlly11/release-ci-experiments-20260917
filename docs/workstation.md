# Workstation setup

Use the section for your operating system, then run the common initialization commands from the
repository root. Git is assumed to be installed. Python-only work needs just Python and uv;
native, analysis, documentation, and coverage tools can be installed when those workflows are needed.

## Requirements

| Tool | Requirement |
| --- | --- |
| Python | 3.12 or newer |
| uv | The root `tool.uv.required-version` constraint |
| CMake | 3.25 or newer |
| Ninja | Required by the presets |
| C / C++ compiler | C17 / C++17; C++ is needed for native tests |
| clang-format / clang-tidy / cppcheck | Required for native analysis |
| Doxygen | 1.9.2 or newer |
| gcov | The same GCC toolchain used for coverage |

CI uses GCC on Linux, Apple Clang on macOS, and MinGW GCC on Windows. Native analysis and coverage
run on Linux. System tools come from your platform or approved development image; Python tool
versions are declared in `pyproject.toml` and resolved in `uv.lock`.

## Ubuntu 24.04 or newer

In Bash, install the native tools and uv:

```bash
sudo apt-get update
sudo apt-get install --yes build-essential cmake ninja-build clang-format clang-tidy cppcheck doxygen curl
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal, or source the environment file named by the uv installer, so `uv` is on PATH.
Select the same compiler family as Linux CI:

```bash
export CC=gcc
export CXX=g++
```

The GCC packages supply gcov. When multiple GCC versions are installed, use matching GCC, G++, and
gcov executables on PATH. The coverage preset explicitly selects `gcc` and `g++`.
See the [official uv installation options](https://docs.astral.sh/uv/getting-started/installation/)
for package-manager and standalone alternatives.

## macOS

Install Apple's command-line developer tools if they are not already present, then use an existing
[Homebrew installation](https://brew.sh/):

```bash
xcode-select --install
brew install uv cmake ninja llvm cppcheck doxygen
export PATH="$(brew --prefix llvm)/bin:$PATH"
export CC=/usr/bin/clang
export CXX=/usr/bin/clang++
```

The explicit compiler paths retain Apple Clang for builds, matching CI. Homebrew's
[LLVM formula](https://formulae.brew.sh/formula/llvm) supplies clang-format and clang-tidy and is
keg-only, so its `bin` directory must be added to PATH. Add the exports to your shell profile if you
want them in new terminals. Run native coverage on Linux; the coverage preset is unavailable on macOS.

## Windows

Install [MSYS2](https://www.msys2.org/), open its **UCRT64** terminal, and update it:

```bash
pacman -Syu
```

If the update closes the terminal, reopen UCRT64 and repeat the command before installing packages:

```bash
pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja
pacman -S --needed mingw-w64-ucrt-x86_64-clang-tools-extra mingw-w64-ucrt-x86_64-cppcheck mingw-w64-ucrt-x86_64-doxygen
```

Use the UCRT64 packages consistently; MSYS2 documents its different
[compiler/runtime environments](https://www.msys2.org/docs/environments/).
The [Clang extra tools package](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-clang-tools-extra)
provides clang-tidy and depends on Clang, which also supplies clang-format.

Install native Windows uv from PowerShell:

```powershell
winget install --id=astral-sh.uv -e
```

Open a new PowerShell terminal and add the native tools to this session's PATH. Adjust the MSYS2
installation path if necessary:

```powershell
$env:Path = "C:\msys64\ucrt64\bin;$env:Path"
$env:CC = "gcc"
$env:CXX = "g++"
Get-Command uv, gcc, g++, cmake, ninja
```

Run the common commands below from PowerShell using uv's managed CPython. Do not use MSYS2's Python
for the workspace. For persistence, add the UCRT64 directory to your user PATH through Windows
environment settings. Native coverage and the sanitizer preset are unavailable on Windows.

## Initialize the checkout

From the repository root, these commands work in Bash, Zsh, and PowerShell:

```text
uv python install 3.12
uv sync --locked --all-packages
uv run repo-tools doctor --profile python
```

Sync installs the private `repo-tools` CLI as an editable development dependency. Run
`uv run repo-tools --help` to discover its commands. The
[package guide](../tools/repo_tools/README.md) explains checkout selection and the plain-Python
launcher used before installation.

For native work, set `CC` and `CXX` before the first CMake configure. Use a fresh build directory
when changing compiler families: an existing cache retains its compiler selection. Check native
prerequisites with `python tools/repo_tools/run.py doctor --profile native`, or use `--profile analysis` for
the static analysis tools. See [native dependency setup](native-quality.md#cpputest-dependency-policy)
for restricted/offline builds.

Install local hooks as described in [Contributing](CONTRIBUTING.md), then follow the
[local validation commands](testing.md#local-validation). Documentation and coverage use optional
uv dependency groups, installed by those commands.

## Understanding doctor output

Run `python tools/repo_tools/run.py doctor --profile all` with an existing Python 3.12+ interpreter for a read-only
check of all system prerequisites. The command itself never installs packages or changes PATH.
Using the `uv run` prefix above can synchronize the workspace before the command starts.

| Profile | Tools checked in addition to the running Python interpreter |
| --- | --- |
| `python` | uv |
| `native` | CMake, Ninja, C and C++ compilers |
| `analysis` | Native tools plus clang-format, clang-tidy, and cppcheck |
| `docs` | uv, CMake, Ninja, C compiler, Doxygen |
| `coverage` | uv, CMake, Ninja, GCC, G++, gcov; requires Linux |
| `all` (default) | All applicable tools; skips native coverage outside Linux |

`OK` includes the executable path and version. `FAIL` identifies missing tools, unsuccessful or
timed-out probes, and known unsupported versions. Fix the reported PATH or installation and rerun.
The command returns 1 if any prerequisite fails and 0 otherwise. Each executable probe times out
after ten seconds. `CC`/`CXX` may name executable paths or compiler launcher commands such as
`ccache gcc`; they are passed as arguments without a shell.

Doctor checks system prerequisites, not Python dependency-group contents or C/C++ language features.
Use `uv sync --locked` with the appropriate group to install Python tools, then run the actual
[quality checks](CONTRIBUTING.md) to validate the resulting toolchain.

The root uv configuration pins setuptools for editable installs and distribution builds.
You do not need to install setuptools globally. See the [backend upgrade procedure](dependencies.md)
when deliberately changing that pin.

## GitHub workflow editing

Run `uv run pre-commit run actionlint --all-files` before submitting workflow changes. The official
hook revision is pinned in `.pre-commit-config.yaml` and uses pre-commit's managed Go environment. First use downloads
and builds the tool and may take longer; subsequent local runs reuse that environment. Allow access
to GitHub and Go toolchain/module downloads when initializing it. Go is a hook build dependency,
not a Python workspace dependency or a requirement for ordinary Python execution.

The system-tool doctor does not inspect pre-commit's private environments. Run the hook itself to
validate its installation. ShellCheck and Pyflakes integration are disabled in this hook.
