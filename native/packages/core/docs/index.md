# Native core

The native core library owns the shared `release_lab_status` contract and bounded message formatter.
Consumers include `<release_lab/core.h>` for behaviour, `<release_lab/core_version.h>` for version macros,
and link to the CMake target `release_lab::core`.

```cmake
target_link_libraries(my_target PRIVATE release_lab::core)
```

## Native core examples

```c
#include <release_lab/core.h>

#include <stdio.h>

int main(void) {
    char message[64] = {0};
    release_lab_status status =
        release_lab_core_format_message("Welcome", "Ada", message, sizeof(message));

    if (status != RELEASE_LAB_STATUS_OK) {
        (void)fprintf(stderr, "%s\n", release_lab_core_status_string(status));
        return 1;
    }

    (void)puts(message);
    return 0;
}
```

Read the configured library version at compile time:

```c
#include <release_lab/core_version.h>

const char *core_version = RELEASE_LAB_CORE_VERSION;
```

Within this repository, save the example as `example.c` and compile it directly with:

```bash
cc -std=c17 -Inative/packages/core/include \
  native/packages/core/src/core.c example.c -o core-example
./core-example
```

## Native core API

```{doxygenenum} release_lab_status
:project: native
```

```{doxygenfunction} release_lab_core_format_message
:project: native
```

```{doxygenfunction} release_lab_core_status_string
:project: native
```

### Version macros

```{doxygendefine} RELEASE_LAB_CORE_VERSION
:project: native
```

```{doxygendefine} RELEASE_LAB_CORE_VERSION_MAJOR
:project: native
```

```{doxygendefine} RELEASE_LAB_CORE_VERSION_MINOR
:project: native
```

```{doxygendefine} RELEASE_LAB_CORE_VERSION_PATCH
:project: native
```
