# Native quality gates

## clang-format

`.clang-format` is the single source of formatting policy for production C, public headers, and
CppUTest C++ sources.

```bash
cmake --build --preset dev --target format-c
cmake --build --preset dev --target format-c-check
```

The first command changes files. The second is read-only and is the appropriate CI gate.

## clang-tidy

`.clang-tidy` enables compiler diagnostics, Clang's static analyzer, CERT-oriented checks, and
portability checks. It is connected to targets through CMake's `C_CLANG_TIDY` target property,
which supplies the exact compiler command and include paths.

## cppcheck

Cppcheck complements clang-tidy with a separate analysis engine. The CMake analysis preset runs
it with warning, style, performance, and portability checks enabled. Missing system includes are
suppressed because those headers are owned by the selected compiler toolchain.

## Policy levels

| Workflow | Intended use | Static analysis |
| --- | --- | --- |
| `dev` | Normal local builds | Available separately; not required |
| `analysis` | Production compilation without tests | clang-tidy and cppcheck required |
| `asan` | Runtime defect detection | AddressSanitizer and UndefinedBehaviorSanitizer |
| `coverage` | Native test effectiveness | GCC/gcov line and branch coverage |
| `release` | Optimized artifacts | Tests and analysis performed in earlier stages |

The sanitizer preset enables AddressSanitizer and UndefinedBehaviorSanitizer for production and
test code. Undefined behavior terminates the process with a failure status, making diagnostics
visible to CTest rather than allowing a successful exit after a runtime error.

Compiler warnings are errors in `dev`, `analysis`, and `asan`. Release consumers do not inherit
the repository's private warning flags.

## CppUTest dependency policy

Native library tests use the core CppUTest framework and continue to run through CTest. CMake
downloads the pinned 4.0 archive only for test-enabled builds, verifies its SHA-256 digest, and
keeps the dependency outside the default install/export set. CppUMock and the extension library
are intentionally disabled until a component has a concrete mocking requirement.

For an approved internal copy, set `FETCHCONTENT_SOURCE_DIR_CPPUTEST` to its extracted source
directory:

```bash
cmake --preset dev -DFETCHCONTENT_SOURCE_DIR_CPPUTEST=/approved/sources/cpputest \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON
```

For the combined Python/native coverage command, pass the source on each invocation:

```bash
uv run --group coverage repo-tools check-coverage --cpputest-source /approved/sources/cpputest
```

This sets both CMake options above after cleaning the coverage build directory. Relative source
paths resolve from the working directory, including when `--project-root` selects another checkout.
Keep the extracted sources outside that checkout's `build/coverage` directory; the command rejects
missing sources, directories without `CMakeLists.txt`, and sources inside the directory it cleans
before changing output. The supplied tree must be the approved CppUTest source described above.
Python dependencies must already be installed or available through an offline uv cache.

Disconnected configuration fails before downloading if no valid local source override or existing
`CppUTest::CppUTest` target is supplied. The `analysis` and `release` presets disable tests and do
not fetch CppUTest. Analysis compiles production targets with clang-tidy/cppcheck; `format-c-check`
still checks all first-party C/C++ files. Unit tests run in the native matrix, coverage, and
sanitizer builds.
Static analysis and coverage target first-party sources rather than downloaded dependency code.
