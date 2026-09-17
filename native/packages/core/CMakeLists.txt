add_library(release_lab_core STATIC src/core.c)
add_library(release_lab::core ALIAS release_lab_core)

target_include_directories(
  release_lab_core
  PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
    "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
monorepo_add_version_header(
  release_lab_core
  "${CMAKE_CURRENT_SOURCE_DIR}/include/release_lab/core_version.h.in"
  "release_lab/core_version.h"
  PUBLIC
)
set_target_properties(release_lab_core PROPERTIES EXPORT_NAME core)
monorepo_set_project_options(release_lab_core)

install(
  TARGETS release_lab_core
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
  add_library(release_lab_core_c_test_helpers OBJECT tests/unknown_status.c)
  target_link_libraries(release_lab_core_c_test_helpers PRIVATE release_lab::core)
  monorepo_set_project_options(release_lab_core_c_test_helpers)

  add_executable(release_lab_core_tests tests/test_core.cpp)
  target_link_libraries(release_lab_core_tests PRIVATE release_lab::core release_lab_cpputest_main release_lab_core_c_test_helpers)
  monorepo_set_cpp_test_options(release_lab_core_tests)
  monorepo_set_version_test_definitions(release_lab_core_tests)
  add_test(NAME c.core COMMAND release_lab_core_tests)
  set_tests_properties(c.core PROPERTIES TIMEOUT 60)
endif()
