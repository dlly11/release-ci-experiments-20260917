include_guard(GLOBAL)

option(WARNINGS_AS_ERRORS "Treat compiler warnings as errors" OFF)
option(ENABLE_SANITIZERS "Enable address and undefined behaviour sanitizers" OFF)
option(ENABLE_COVERAGE "Instrument native targets for GCC coverage reporting" OFF)

function(monorepo_set_instrumentation target language)
  if(ENABLE_SANITIZERS)
    if(MSVC)
      message(FATAL_ERROR "The sanitizer preset is currently supported only with GCC or Clang")
    endif()
    target_compile_options(
      ${target} PRIVATE -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer
    )
    target_link_options(${target} PRIVATE -fsanitize=address,undefined)
  endif()

  if(ENABLE_COVERAGE)
    if(ENABLE_SANITIZERS)
      message(FATAL_ERROR "Coverage and sanitizer instrumentation cannot be enabled together")
    endif()
    if(NOT CMAKE_${language}_COMPILER_ID STREQUAL "GNU")
      message(FATAL_ERROR "Native coverage requires GNU compilers and gcov")
    endif()

    target_compile_options(${target} PRIVATE --coverage -Og -g)
    get_target_property(monorepo_target_type ${target} TYPE)
    if(NOT monorepo_target_type STREQUAL "STATIC_LIBRARY")
      target_link_options(${target} PRIVATE --coverage)
    endif()
  endif()
endfunction()

function(monorepo_set_project_options target)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4)
    if(WARNINGS_AS_ERRORS)
      target_compile_options(${target} PRIVATE /WX)
    endif()
  else()
    target_compile_options(
      ${target}
      PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Wconversion
        -Wshadow
        -Wstrict-prototypes
        -Wmissing-prototypes
    )
    if(WARNINGS_AS_ERRORS)
      target_compile_options(${target} PRIVATE -Werror)
    endif()
  endif()

  set_target_properties(
    ${target}
    PROPERTIES
      C_STANDARD 17
      C_STANDARD_REQUIRED YES
      C_EXTENSIONS NO
  )

  monorepo_set_instrumentation(${target} C)

  monorepo_enable_static_analysis(${target})
endfunction()

function(monorepo_set_cpp_test_options target)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4)
    if(WARNINGS_AS_ERRORS)
      target_compile_options(${target} PRIVATE /WX)
    endif()
  else()
    target_compile_options(
      ${target}
      PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Wconversion
        -Wshadow
    )
    if(WARNINGS_AS_ERRORS)
      target_compile_options(${target} PRIVATE -Werror)
    endif()
    if(
      CMAKE_CXX_COMPILER_ID STREQUAL "GNU"
      AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 15.1
    )
      target_compile_options(${target} PRIVATE -fno-assume-sane-operators-new-delete)
    endif()
  endif()

  set_target_properties(
    ${target}
    PROPERTIES
      CXX_STANDARD 17
      CXX_STANDARD_REQUIRED YES
      CXX_EXTENSIONS NO
  )

  monorepo_set_instrumentation(${target} CXX)
endfunction()
