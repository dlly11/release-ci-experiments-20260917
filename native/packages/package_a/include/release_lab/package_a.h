#ifndef RELEASE_LAB_PACKAGE_A_H
#define RELEASE_LAB_PACKAGE_A_H

#include "release_lab/core.h"

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Create a greeting using the shared core formatter.
 *
 * The input, output, and failure contracts are the same as
 * release_lab_core_format_message().
 *
 * @param[in] name Non-empty recipient name.
 * @param[out] output Destination buffer.
 * @param[in] output_capacity Size of @p output in bytes.
 * @return RELEASE_LAB_STATUS_OK on success, or a status describing the failure.
 */
release_lab_status release_lab_package_a_greeting(const char *name, char *output,
                                                  size_t output_capacity);

#ifdef __cplusplus
}
#endif

#endif
