#include <cmath>
#include <gtest/gtest.h>

#include "pluton/primitives.h"

namespace {

::testing::AssertionResult NearlyEqual(float a, float b, float tol = 1e-5f) {
    if (std::abs(a - b) <= tol) return ::testing::AssertionSuccess();
    return ::testing::AssertionFailure() << a << " not within " << tol << " of " << b;
}

}  // namespace

TEST(PrimitivesCube, CountsAreCorrect) {
    const auto cube = pluton::make_cube(1.0f);
    EXPECT_EQ(cube.vertex_count(), 24u);
    EXPECT_EQ(cube.triangle_count(), 12u);
    EXPECT_EQ(cube.indices.size(), 36u);
    EXPECT_EQ(cube.positions.size(), 72u);
    EXPECT_EQ(cube.normals.size(), 72u);
}

TEST(PrimitivesCube, BottomOnGroundCentered) {
    const float size = 2.5f;
    const auto cube = pluton::make_cube(size);

    for (std::size_t i = 0; i < cube.vertex_count(); ++i) {
        const float x = cube.positions[3 * i + 0];
        const float y = cube.positions[3 * i + 1];
        const float z = cube.positions[3 * i + 2];
        EXPECT_GE(x, -size / 2 - 1e-5f);
        EXPECT_LE(x, +size / 2 + 1e-5f);
        EXPECT_GE(y, -size / 2 - 1e-5f);
        EXPECT_LE(y, +size / 2 + 1e-5f);
        EXPECT_GE(z, 0.0f - 1e-5f);
        EXPECT_LE(z, size + 1e-5f);
    }
}

TEST(PrimitivesCube, AllNormalsAreUnitLength) {
    const auto cube = pluton::make_cube(1.0f);
    for (std::size_t i = 0; i < cube.vertex_count(); ++i) {
        const float nx = cube.normals[3 * i + 0];
        const float ny = cube.normals[3 * i + 1];
        const float nz = cube.normals[3 * i + 2];
        const float length = std::sqrt(nx * nx + ny * ny + nz * nz);
        EXPECT_TRUE(NearlyEqual(length, 1.0f)) << "vertex " << i;
    }
}

TEST(PrimitivesCube, IndicesAreInRange) {
    const auto cube = pluton::make_cube(1.0f);
    for (std::uint32_t idx : cube.indices) {
        EXPECT_LT(idx, cube.vertex_count());
    }
}

TEST(PrimitivesCube, EachFaceHasOneNormal) {
    const auto cube = pluton::make_cube(1.0f);
    for (std::size_t f = 0; f < 6; ++f) {
        const float nx0 = cube.normals[3 * (4 * f + 0) + 0];
        const float ny0 = cube.normals[3 * (4 * f + 0) + 1];
        const float nz0 = cube.normals[3 * (4 * f + 0) + 2];
        for (std::size_t v = 1; v < 4; ++v) {
            EXPECT_TRUE(NearlyEqual(cube.normals[3 * (4 * f + v) + 0], nx0));
            EXPECT_TRUE(NearlyEqual(cube.normals[3 * (4 * f + v) + 1], ny0));
            EXPECT_TRUE(NearlyEqual(cube.normals[3 * (4 * f + v) + 2], nz0));
        }
    }
}
