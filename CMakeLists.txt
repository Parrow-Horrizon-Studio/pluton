cmake_minimum_required(VERSION 3.27)

# Project metadata
project(pluton
    VERSION 0.1.8
    DESCRIPTION "Polygonal 3D modeler for architecture"
    LANGUAGES CXX
)

# Require C++20 globally
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Generate compile_commands.json for IDE support (clangd, etc.)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Compiler warning baseline
if(MSVC)
    add_compile_options(/W4)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find Python (driven by scikit-build-core at build time)
find_package(Python 3.13 COMPONENTS Interpreter Development.Module REQUIRED)

# Find nanobind (installed via pip as a build dep — scikit-build-core handles this)
find_package(nanobind CONFIG REQUIRED)

# Add C++ source tree
add_subdirectory(cpp)

# Enable tests if this is the top-level project (not when consumed as a subproject)
# and the cpp/tests directory exists (it's added in M0 Task 10).
if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/cpp/tests/CMakeLists.txt")
    enable_testing()
    add_subdirectory(cpp/tests)
endif()
