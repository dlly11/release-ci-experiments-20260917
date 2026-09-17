# Expected streams are exact strings, including any final newline. An omitted argument
# invokes the command with no arguments; a defined empty argument passes an empty string.
foreach(required_variable COMMAND_PATH EXPECTED_EXIT_CODE EXPECTED_STDOUT EXPECTED_STDERR)
  if(NOT DEFINED ${required_variable})
    message(FATAL_ERROR "${required_variable} is required")
  endif()
endforeach()
if(NOT EXPECTED_EXIT_CODE MATCHES "^[0-9]+$")
  message(FATAL_ERROR "EXPECTED_EXIT_CODE must be a non-negative integer")
endif()

set(command_output "")
set(output_option OUTPUT_VARIABLE command_output)
if(DEFINED STDOUT_FILE)
  if(NOT EXPECTED_STDOUT STREQUAL "")
    message(FATAL_ERROR "EXPECTED_STDOUT must be empty when STDOUT_FILE is supplied")
  endif()
  set(output_option OUTPUT_FILE "${STDOUT_FILE}")
endif()

if(DEFINED COMMAND_ARGUMENT)
  execute_process(
    COMMAND "${COMMAND_PATH}" "${COMMAND_ARGUMENT}"
    RESULT_VARIABLE command_status
    ${output_option}
    ERROR_VARIABLE command_error
    TIMEOUT 10
  )
else()
  execute_process(
    COMMAND "${COMMAND_PATH}"
    RESULT_VARIABLE command_status
    ${output_option}
    ERROR_VARIABLE command_error
    TIMEOUT 10
  )
endif()

if(command_status MATCHES "[Tt]imeout")
  message(FATAL_ERROR "Command '${COMMAND_PATH}' exceeded its 10-second timeout: ${command_error}")
endif()

# A string comparison also rejects process-launch errors and signal descriptions.
if(NOT command_status STREQUAL "${EXPECTED_EXIT_CODE}")
  message(FATAL_ERROR "Expected exit ${EXPECTED_EXIT_CODE}, received ${command_status}: ${command_error}")
endif()

string(REPLACE "\r\n" "\n" normalized_output "${command_output}")
string(REPLACE "\r\n" "\n" normalized_error "${command_error}")
if(NOT normalized_output STREQUAL "${EXPECTED_STDOUT}")
  message(FATAL_ERROR "Expected stdout '${EXPECTED_STDOUT}', received '${normalized_output}'")
endif()
if(NOT normalized_error STREQUAL "${EXPECTED_STDERR}")
  message(FATAL_ERROR "Expected stderr '${EXPECTED_STDERR}', received '${normalized_error}'")
endif()
