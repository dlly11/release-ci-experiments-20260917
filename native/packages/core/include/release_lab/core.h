#ifndef RELEASE_LAB_CORE_H
#define RELEASE_LAB_CORE_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Status returned by the example native APIs. */
typedef enum release_lab_status {
    /** The operation completed successfully. */
    RELEASE_LAB_STATUS_OK = 0,
    /** A required pointer, string, or capacity was invalid. */
    RELEASE_LAB_STATUS_INVALID_ARGUMENT = 1,
    /** The output buffer could not hold the complete formatted message. */
    RELEASE_LAB_STATUS_BUFFER_TOO_SMALL = 2,
    /** The C runtime could not format the message. */
    RELEASE_LAB_STATUS_FORMAT_ERROR = 3
} release_lab_status;

/**
 * Format a message as ``prefix, name!``.
 *
 * Inputs must be null-terminated and must not overlap the output buffer.
 * On success, output contains the complete null-terminated message. If the buffer
 * is too small, output contains a null-terminated partial message. Invalid arguments
 * leave the supplied output untouched. A formatting error sets output[0] to zero.
 *
 * @param[in] prefix Non-empty message prefix.
 * @param[in] name Non-empty recipient name.
 * @param[out] output Destination buffer.
 * @param[in] output_capacity Size of @p output in bytes.
 * @return RELEASE_LAB_STATUS_OK on success, or a status describing the failure.
 */
release_lab_status release_lab_core_format_message(const char *prefix, const char *name,
                                                   char *output, size_t output_capacity);

/**
 * Return a stable human-readable description of a status.
 *
 * @param[in] status Status to describe.
 * @return A pointer to a static, null-terminated string.
 */
const char *release_lab_core_status_string(release_lab_status status);

#ifdef __cplusplus
}
#endif

#endif
