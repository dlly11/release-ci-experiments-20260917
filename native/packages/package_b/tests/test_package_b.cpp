#include "CppUTest/TestHarness.h"

#include "release_lab/package_b.h"
#include "release_lab/package_b_version.h"

TEST_GROUP(PackageBFarewell){};

TEST(PackageBFarewell, CreatesFarewell) {
    char output[64] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_OK,
                release_lab_package_b_farewell("Ada", output, sizeof(output)));
    STRCMP_EQUAL("Goodbye, Ada!", output);
}

TEST_GROUP(PackageBVersion){};

TEST(PackageBVersion, MatchesRepositoryVersion) {
    STRCMP_EQUAL(RELEASE_LAB_EXPECTED_VERSION, RELEASE_LAB_PACKAGE_B_VERSION);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_MAJOR, RELEASE_LAB_PACKAGE_B_VERSION_MAJOR);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_MINOR, RELEASE_LAB_PACKAGE_B_VERSION_MINOR);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_PATCH, RELEASE_LAB_PACKAGE_B_VERSION_PATCH);
}
