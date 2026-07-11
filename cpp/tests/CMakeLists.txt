find_package(GTest CONFIG REQUIRED)

add_executable(pluton_tests
    test_version.cpp
    test_mesh.cpp
    test_primitives.cpp
    test_halfedge.cpp
    test_ray_intersect.cpp
    test_gltf_import.cpp
)

target_compile_definitions(pluton_tests PRIVATE
    PLUTON_TEST_DATA="${CMAKE_SOURCE_DIR}/tests/data")

target_link_libraries(pluton_tests PRIVATE
    pluton_core
    GTest::gtest
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(pluton_tests)
