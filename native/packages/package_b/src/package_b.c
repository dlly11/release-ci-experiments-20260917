#include "release_lab/package_b.h"

release_lab_status release_lab_package_b_farewell(const char *name, char *output,
                                                  size_t output_capacity) {
    return release_lab_core_format_message("Goodbye", name, output, output_capacity);
}
