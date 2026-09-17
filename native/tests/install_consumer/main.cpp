#include "release_lab/core.h"
#include "release_lab/core_version.h"
#include "release_lab/package_a.h"
#include "release_lab/package_a_cli_version.h"
#include "release_lab/package_a_version.h"
#include "release_lab/package_b.h"
#include "release_lab/package_b_version.h"

#include <cstring>

int main() {
    char greeting[64] = {0};
    char farewell[64] = {0};

    if (release_lab_package_a_greeting("Ada", greeting, sizeof(greeting)) !=
            RELEASE_LAB_STATUS_OK ||
        release_lab_package_b_farewell("Ada", farewell, sizeof(farewell)) !=
            RELEASE_LAB_STATUS_OK) {
        return 1;
    }
    if (std::strcmp(greeting, "Hello, Ada!") != 0 || std::strcmp(farewell, "Goodbye, Ada!") != 0) {
        return 2;
    }
    if (std::strcmp(RELEASE_LAB_CORE_VERSION, RELEASE_LAB_PACKAGE_A_VERSION) != 0 ||
        std::strcmp(RELEASE_LAB_CORE_VERSION, RELEASE_LAB_PACKAGE_B_VERSION) != 0 ||
        std::strcmp(RELEASE_LAB_CORE_VERSION, RELEASE_LAB_PACKAGE_A_CLI_VERSION) != 0) {
        return 3;
    }
    return 0;
}
