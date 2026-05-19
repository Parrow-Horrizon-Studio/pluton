# Core library — the C++ implementation
add_library(pluton_core STATIC
    src/version.cpp
    src/mesh.cpp
    src/primitives.cpp
)

target_include_directories(pluton_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Position-independent code required when linking into a Python module
set_target_properties(pluton_core PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

# The nanobind module — exposed to Python as `pluton._core`
nanobind_add_module(_core
    bindings/module.cpp
)

target_link_libraries(_core PRIVATE pluton_core)

# Install the compiled module into the Python package directory
install(TARGETS _core LIBRARY DESTINATION pluton)
