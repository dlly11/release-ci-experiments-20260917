include_guard(GLOBAL)

function(monorepo_add_version_header target template relative_header visibility)
  if(NOT TARGET ${target})
    message(FATAL_ERROR "Cannot add a version header to unknown target: ${target}")
  endif()

  set(generated_include_directory "${CMAKE_BINARY_DIR}/generated/include")
  set(generated_header "${generated_include_directory}/${relative_header}")
  get_filename_component(generated_header_directory "${generated_header}" DIRECTORY)
  get_filename_component(install_header_directory "${relative_header}" DIRECTORY)

  file(MAKE_DIRECTORY "${generated_header_directory}")
  configure_file("${template}" "${generated_header}" @ONLY)

  target_include_directories(
    ${target}
    ${visibility}
      "$<BUILD_INTERFACE:${generated_include_directory}>"
  )
  install(
    FILES "${generated_header}"
    DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}/${install_header_directory}"
  )
endfunction()

function(monorepo_set_version_test_definitions target)
  target_compile_definitions(
    ${target}
    PRIVATE
      RELEASE_LAB_EXPECTED_VERSION="${CMAKE_PROJECT_VERSION}"
      RELEASE_LAB_EXPECTED_VERSION_MAJOR=${CMAKE_PROJECT_VERSION_MAJOR}
      RELEASE_LAB_EXPECTED_VERSION_MINOR=${CMAKE_PROJECT_VERSION_MINOR}
      RELEASE_LAB_EXPECTED_VERSION_PATCH=${CMAKE_PROJECT_VERSION_PATCH}
  )
endfunction()
