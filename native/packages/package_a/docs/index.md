# Native package A

The native package A library creates greetings through the core formatter. Consumers include
`<release_lab/package_a.h>` for behaviour, `<release_lab/package_a_version.h>` for version macros, and link
to `release_lab::package_a`.

```cmake
target_link_libraries(my_target PRIVATE release_lab::package_a)
```

## Native package A examples

```c
#include <release_lab/package_a.h>

#include <stdio.h>

int main(void) {
    char message[64] = {0};
    release_lab_status status = release_lab_package_a_greeting("Ada", message, sizeof(message));

    if (status != RELEASE_LAB_STATUS_OK) {
        return 1;
    }

    (void)puts(message);
    return 0;
}
```

Read the configured package version at compile time:

```c
#include <release_lab/package_a_version.h>

const char *package_a_version = RELEASE_LAB_PACKAGE_A_VERSION;
```

Within this repository, save the example as `example.c` and compile it directly with:

```bash
cc -std=c17 -Inative/packages/core/include -Inative/packages/package_a/include \
  native/packages/core/src/core.c native/packages/package_a/src/package_a.c \
  example.c -o package-a-example
./package-a-example
```

## Native package A API

```{doxygenfunction} release_lab_package_a_greeting
:project: native
```

### Version macros

```{doxygendefine} RELEASE_LAB_PACKAGE_A_VERSION
:project: native
```

```{doxygendefine} RELEASE_LAB_PACKAGE_A_VERSION_MAJOR
:project: native
```

```{doxygendefine} RELEASE_LAB_PACKAGE_A_VERSION_MINOR
:project: native
```

```{doxygendefine} RELEASE_LAB_PACKAGE_A_VERSION_PATCH
:project: native
```
