#include "release_lab/core.h"

const char *release_lab_test_unknown_status_string(void);

/* C permits this value; converting 99 to this enum in C++ would be undefined. */
const char *release_lab_test_unknown_status_string(void) {
    return release_lab_core_status_string((release_lab_status)99);
}
