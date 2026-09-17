include_guard(GLOBAL)

option(ENABLE_CLANG_TIDY "Run clang-tidy while compiling C targets" OFF)
option(ENABLE_CPPCHECK "Run cppcheck while compiling C targets" OFF)
option(
  REQUIRE_ANALYSIS_TOOLS
  "Fail configuration when a requested static-analysis tool is unavailable"
  OFF
)

function(_monorepo_find_tool output_variable tool_name)
  find_program(_tool_path NAMES "${tool_name}")
  if(NOT _tool_path AND REQUIRE_ANALYSIS_TOOLS)
    message(FATAL_ERROR "Required static-analysis tool was not found: ${tool_name}")
  endif()
  set(${output_variable} "${_tool_path}" PARENT_SCOPE)
  unset(_tool_path CACHE)
endfunction()

function(monorepo_enable_static_analysis target)
  if(ENABLE_CLANG_TIDY)
    _monorepo_find_tool(clang_tidy_executable clang-tidy)
    if(clang_tidy_executable)
      set_target_properties(
        ${target}
        PROPERTIES
          C_CLANG_TIDY
            "${clang_tidy_executable};--config-file=${PROJECT_SOURCE_DIR}/.clang-tidy"
      )
    endif()
  endif()

  if(ENABLE_CPPCHECK)
    _monorepo_find_tool(cppcheck_executable cppcheck)
    if(cppcheck_executable)
      set_target_properties(
        ${target}
        PROPERTIES
          C_CPPCHECK
            "${cppcheck_executable};--enable=warning,style,performance,portability;--std=c17;--inline-suppr;--error-exitcode=1;--suppress=missingIncludeSystem"
      )
    endif()
  endif()
endfunction()

function(monorepo_add_clang_format_targets)
  file(
    GLOB_RECURSE monorepo_native_sources
    CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/native/*.c"
    "${PROJECT_SOURCE_DIR}/native/*.cpp"
    "${PROJECT_SOURCE_DIR}/native/*.h"
  )

  _monorepo_find_tool(clang_format_executable clang-format)
  if(NOT clang_format_executable)
    message(STATUS "clang-format not found; format-c targets will not be available")
    return()
  endif()

  add_custom_target(
    format-c
    COMMAND "${clang_format_executable}" -i ${monorepo_native_sources}
    COMMENT "Formatting first-party native sources with clang-format"
    VERBATIM
  )
  add_custom_target(
    format-c-check
    COMMAND "${clang_format_executable}" --dry-run --Werror ${monorepo_native_sources}
    COMMENT "Checking first-party native formatting with clang-format"
    VERBATIM
  )
endfunction()
