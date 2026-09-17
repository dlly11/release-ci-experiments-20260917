cmake_minimum_required(VERSION 3.25)

project(
  release_lab
  VERSION 0.2.1 # x-release-please-version
  DESCRIPTION "Production-oriented C component examples"
  LANGUAGES C
)

include(GNUInstallDirs)
include(CTest)
include(CMakePackageConfigHelpers)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(ProjectOptions)
include(StaticAnalysis)
include(VersionHeaders)

monorepo_add_clang_format_targets()

if(BUILD_TESTING)
  enable_language(CXX)
  include(CppUTest)
  monorepo_add_cpputest()

  add_library(release_lab_cpputest_main STATIC native/tests/cpputest_main.cpp)
  target_link_libraries(release_lab_cpputest_main PUBLIC CppUTest::CppUTest)
  monorepo_set_cpp_test_options(release_lab_cpputest_main)
endif()

add_subdirectory(native/packages/core)
add_subdirectory(native/packages/package_a)
add_subdirectory(native/packages/package_b)
add_subdirectory(native/apps/package_a_cli)

set(monorepo_cmake_install_directory "${CMAKE_INSTALL_LIBDIR}/cmake/ReleaseLab")
configure_package_config_file(
  cmake/ReleaseLabConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/ReleaseLabConfig.cmake"
  INSTALL_DESTINATION "${monorepo_cmake_install_directory}"
)
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/ReleaseLabConfigVersion.cmake"
  VERSION "${PROJECT_VERSION}"
  COMPATIBILITY SameMajorVersion
)

install(
  EXPORT ReleaseLabTargets
  FILE ReleaseLabTargets.cmake
  NAMESPACE release_lab::
  DESTINATION "${monorepo_cmake_install_directory}"
)
install(
  FILES
    "${CMAKE_CURRENT_BINARY_DIR}/ReleaseLabConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/ReleaseLabConfigVersion.cmake"
  DESTINATION "${monorepo_cmake_install_directory}"
)

install(FILES LICENSE DESTINATION "${CMAKE_INSTALL_DATADIR}/licenses/release-ci-experiments-20260917")
