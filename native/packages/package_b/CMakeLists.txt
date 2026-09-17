add_library(release_lab_package_b STATIC src/package_b.c)
add_library(release_lab::package_b ALIAS release_lab_package_b)

target_include_directories(
  release_lab_package_b
  PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
    "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
monorepo_add_version_header(
  release_lab_package_b
  "${CMAKE_CURRENT_SOURCE_DIR}/include/release_lab/package_b_version.h.in"
  "release_lab/package_b_version.h"
  PUBLIC
)
target_link_libraries(release_lab_package_b PUBLIC release_lab::core)
set_target_properties(release_lab_package_b PROPERTIES EXPORT_NAME package_b)
monorepo_set_project_options(release_lab_package_b)

install(
  TARGETS release_lab_package_b
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
  add_executable(release_lab_package_b_tests tests/test_package_b.cpp)
  target_link_libraries(release_lab_package_b_tests PRIVATE release_lab::package_b release_lab_cpputest_main)
  monorepo_set_cpp_test_options(release_lab_package_b_tests)
  monorepo_set_version_test_definitions(release_lab_package_b_tests)
  add_test(NAME c.package_b COMMAND release_lab_package_b_tests)
  set_tests_properties(c.package_b PROPERTIES TIMEOUT 60)
endif()
