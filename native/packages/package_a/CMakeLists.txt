add_library(release_lab_package_a STATIC src/package_a.c)
add_library(release_lab::package_a ALIAS release_lab_package_a)

target_include_directories(
  release_lab_package_a
  PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
    "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
monorepo_add_version_header(
  release_lab_package_a
  "${CMAKE_CURRENT_SOURCE_DIR}/include/release_lab/package_a_version.h.in"
  "release_lab/package_a_version.h"
  PUBLIC
)
target_link_libraries(release_lab_package_a PUBLIC release_lab::core)
set_target_properties(release_lab_package_a PROPERTIES EXPORT_NAME package_a)
monorepo_set_project_options(release_lab_package_a)

install(
  TARGETS release_lab_package_a
  EXPORT ReleaseLabTargets
  ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}"
  INCLUDES DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}"
)
install(
  DIRECTORY include/
  DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}"
  FILES_MATCHING
  PATTERN "*.h"
)

if(BUILD_TESTING)
  add_executable(release_lab_package_a_tests tests/test_package_a.cpp)
  target_link_libraries(release_lab_package_a_tests PRIVATE release_lab::package_a release_lab_cpputest_main)
  monorepo_set_cpp_test_options(release_lab_package_a_tests)
  monorepo_set_version_test_definitions(release_lab_package_a_tests)
  add_test(NAME c.package_a COMMAND release_lab_package_a_tests)
  set_tests_properties(c.package_a PROPERTIES TIMEOUT 60)
endif()
