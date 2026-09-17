cmake_minimum_required(VERSION 3.25)

project(native_install_consumer LANGUAGES CXX)

if(NOT MONOREPO_INSTALL_PREFIX)
  message(FATAL_ERROR "Set MONOREPO_INSTALL_PREFIX to the installation being tested")
endif()
# Do not allow a previous configure or a system installation to satisfy this smoke test.
unset(ReleaseLab_DIR CACHE)
find_package(
  ReleaseLab CONFIG REQUIRED
  PATHS "${MONOREPO_INSTALL_PREFIX}"
  NO_DEFAULT_PATH
  NO_CMAKE_FIND_ROOT_PATH
)

add_executable(native_install_consumer main.cpp)
target_compile_features(native_install_consumer PRIVATE cxx_std_17)
target_link_libraries(
  native_install_consumer
  PRIVATE
    release_lab::package_a
    release_lab::package_b
)

enable_testing()
add_test(NAME installed.native.cpp_consumer COMMAND native_install_consumer)
set_tests_properties(installed.native.cpp_consumer PROPERTIES TIMEOUT 60)
