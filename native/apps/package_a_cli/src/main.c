#include "release_lab/package_a.h"
#include "release_lab/package_a_cli_version.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    char output[256] = {0};
    release_lab_status status = RELEASE_LAB_STATUS_OK;

    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        if (printf("release-lab-package-a-cli %s\n", RELEASE_LAB_PACKAGE_A_CLI_VERSION) < 0 ||
            fflush(stdout) == EOF) {
            return EXIT_FAILURE;
        }
        return EXIT_SUCCESS;
    }

    if (argc != 2) {
        (void)fprintf(stderr, "usage: %s NAME\n", argv[0]);
        return EXIT_FAILURE;
    }

    status = release_lab_package_a_greeting(argv[1], output, sizeof(output));
    if (status != RELEASE_LAB_STATUS_OK) {
        (void)fprintf(stderr, "release-lab-package-a-cli: %s\n",
                      release_lab_core_status_string(status));
        return EXIT_FAILURE;
    }

    if (puts(output) == EOF || fflush(stdout) == EOF) {
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
