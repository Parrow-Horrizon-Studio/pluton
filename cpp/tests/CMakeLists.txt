find_package(GTest CONFIG REQUIRED)

add_executable(pluton_tests
    test_version.cpp
    test_mesh.cpp
)

target_link_libraries(pluton_tests PRIVATE
    pluton_core
    GTest::gtest
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(pluton_tests)
