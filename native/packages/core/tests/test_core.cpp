#include "CppUTest/TestHarness.h"

#include "release_lab/core.h"
#include "release_lab/core_version.h"

extern "C" const char *release_lab_test_unknown_status_string(void);

TEST_GROUP(CoreFormatMessage){};

TEST(CoreFormatMessage, FormatsMessage) {
    char output[64] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_OK,
                release_lab_core_format_message("Hello", "Ada", output, sizeof(output)));
    STRCMP_EQUAL("Hello, Ada!", output);
}

TEST(CoreFormatMessage, ReportsSmallOutputBuffer) {
    char output[4] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_BUFFER_TOO_SMALL,
                release_lab_core_format_message("Hello", "Ada", output, sizeof(output)));
}

TEST(CoreFormatMessage, AcceptsExactFit) {
    char output[sizeof("Hello, Ada!")] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_OK,
                release_lab_core_format_message("Hello", "Ada", output, sizeof(output)));
    STRCMP_EQUAL("Hello, Ada!", output);
}

TEST(CoreFormatMessage, TerminatesOutputOneByteShort) {
    char output[sizeof("Hello, Ada!") - 1U] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_BUFFER_TOO_SMALL,
                release_lab_core_format_message("Hello", "Ada", output, sizeof(output)));
    STRCMP_EQUAL("Hello, Ada", output);
}

TEST(CoreFormatMessage, TerminatesSingleByteOutput) {
    char output[1] = {'x'};

    LONGS_EQUAL(RELEASE_LAB_STATUS_BUFFER_TOO_SMALL,
                release_lab_core_format_message("Hello", "Ada", output, sizeof(output)));
    STRCMP_EQUAL("", output);
}

TEST(CoreFormatMessage, LeavesOutputUntouchedAfterValidationFailure) {
    char output[] = "unchanged";

    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("Hello", "", output, sizeof(output)));
    STRCMP_EQUAL("unchanged", output);
    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("Hello", "Ada", output, 0U));
    STRCMP_EQUAL("unchanged", output);
}

TEST(CoreFormatMessage, RejectsInvalidArguments) {
    char output[64] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message(nullptr, "Ada", output, sizeof(output)));
    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("Hello", nullptr, output, sizeof(output)));
    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("Hello", "Ada", nullptr, sizeof(output)));
    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("Hello", "Ada", output, 0U));
    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("", "Ada", output, sizeof(output)));
    LONGS_EQUAL(RELEASE_LAB_STATUS_INVALID_ARGUMENT,
                release_lab_core_format_message("Hello", "", output, sizeof(output)));
}

TEST_GROUP(CoreStatusString){};

TEST(CoreStatusString, DescribesEveryStatus) {
    STRCMP_EQUAL("ok", release_lab_core_status_string(RELEASE_LAB_STATUS_OK));
    STRCMP_EQUAL("invalid argument",
                 release_lab_core_status_string(RELEASE_LAB_STATUS_INVALID_ARGUMENT));
    STRCMP_EQUAL("buffer too small",
                 release_lab_core_status_string(RELEASE_LAB_STATUS_BUFFER_TOO_SMALL));
    STRCMP_EQUAL("format error", release_lab_core_status_string(RELEASE_LAB_STATUS_FORMAT_ERROR));
    STRCMP_EQUAL("unknown status", release_lab_test_unknown_status_string());
}

TEST_GROUP(CoreVersion){};

TEST(CoreVersion, MatchesRepositoryVersion) {
    STRCMP_EQUAL(RELEASE_LAB_EXPECTED_VERSION, RELEASE_LAB_CORE_VERSION);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_MAJOR, RELEASE_LAB_CORE_VERSION_MAJOR);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_MINOR, RELEASE_LAB_CORE_VERSION_MINOR);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_PATCH, RELEASE_LAB_CORE_VERSION_PATCH);
}
