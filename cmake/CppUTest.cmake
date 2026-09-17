include_guard(GLOBAL)

include(FetchContent)

function(monorepo_add_cpputest)
  if(TARGET CppUTest::CppUTest)
    return()
  endif()

  if(FETCHCONTENT_SOURCE_DIR_CPPUTEST)
    get_filename_component(
      cpputest_SOURCE_DIR
      "${FETCHCONTENT_SOURCE_DIR_CPPUTEST}"
      ABSOLUTE
      BASE_DIR "${CMAKE_SOURCE_DIR}"
    )
    set(cpputest_BINARY_DIR "${FETCHCONTENT_BASE_DIR}/cpputest-build")
    if(NOT EXISTS "${cpputest_SOURCE_DIR}/CMakeLists.txt")
      message(
        FATAL_ERROR
        "FETCHCONTENT_SOURCE_DIR_CPPUTEST does not contain a CppUTest source tree: "
        "${cpputest_SOURCE_DIR}"
      )
    endif()
  elseif(FETCHCONTENT_FULLY_DISCONNECTED)
    message(
      FATAL_ERROR
      "Disconnected builds require FETCHCONTENT_SOURCE_DIR_CPPUTEST pointing to a local "
      "CppUTest source tree, or an existing CppUTest::CppUTest target"
    )
  else()
    FetchContent_Populate(
      CppUTest
      URL https://github.com/cpputest/cpputest/releases/download/v4.0/cpputest-4.0.tar.gz
      URL_HASH SHA256=21c692105db15299b5529af81a11a7ad80397f92c122bd7bf1e4a4b0e85654f7
      DOWNLOAD_EXTRACT_TIMESTAMP FALSE
    )
  endif()

  # CppUTest 4.0 predates namespaced options. Normal variables plus this policy default keep
  # its generic options out of this project's cache while disabling unneeded upstream targets.
  set(CMAKE_POLICY_DEFAULT_CMP0077 NEW)
  set(TESTS OFF)
  set(EXTENSIONS OFF)
  set(EXAMPLES OFF)
  set(VERBOSE_CONFIG OFF)

  # CMake 4 requires dependencies with older policy declarations to select a supported floor.
  if(CMAKE_VERSION VERSION_GREATER_EQUAL 4.0)
    set(CMAKE_POLICY_VERSION_MINIMUM 3.10)
  endif()

  # GCC 15 assumes replaceable new/delete operators have standard semantics unless told otherwise.
  if(
    CMAKE_CXX_COMPILER_ID STREQUAL "GNU"
    AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 15.1
  )
    string(APPEND CMAKE_CXX_FLAGS " -fno-assume-sane-operators-new-delete")
  endif()

  add_subdirectory(
    "${cpputest_SOURCE_DIR}"
    "${cpputest_BINARY_DIR}"
    EXCLUDE_FROM_ALL
    SYSTEM
  )

  if(NOT TARGET CppUTest::CppUTest)
    add_library(CppUTest::CppUTest ALIAS CppUTest)
  endif()
endfunction()
