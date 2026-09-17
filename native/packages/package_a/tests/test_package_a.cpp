#include "CppUTest/TestHarness.h"

#include "release_lab/package_a.h"
#include "release_lab/package_a_version.h"

TEST_GROUP(PackageAGreeting){};

TEST(PackageAGreeting, CreatesGreeting) {
    char output[64] = {0};

    LONGS_EQUAL(RELEASE_LAB_STATUS_OK,
                release_lab_package_a_greeting("Ada", output, sizeof(output)));
    STRCMP_EQUAL("Hello, Ada!", output);
}

TEST_GROUP(PackageAVersion){};

TEST(PackageAVersion, MatchesRepositoryVersion) {
    STRCMP_EQUAL(RELEASE_LAB_EXPECTED_VERSION, RELEASE_LAB_PACKAGE_A_VERSION);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_MAJOR, RELEASE_LAB_PACKAGE_A_VERSION_MAJOR);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_MINOR, RELEASE_LAB_PACKAGE_A_VERSION_MINOR);
    LONGS_EQUAL(RELEASE_LAB_EXPECTED_VERSION_PATCH, RELEASE_LAB_PACKAGE_A_VERSION_PATCH);
}
