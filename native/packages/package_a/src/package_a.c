#include "release_lab/package_a.h"

release_lab_status release_lab_package_a_greeting(const char *name, char *output,
                                                  size_t output_capacity) {
    return release_lab_core_format_message("Hello", name, output, output_capacity);
}
