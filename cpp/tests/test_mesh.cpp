#include <gtest/gtest.h>

#include "pluton/mesh.h"

TEST(MeshTest, DefaultConstructedIsEmpty) {
    pluton::Mesh m;
    EXPECT_EQ(m.vertex_count(), 0u);
    EXPECT_EQ(m.triangle_count(), 0u);
    EXPECT_TRUE(m.positions.empty());
    EXPECT_TRUE(m.normals.empty());
    EXPECT_TRUE(m.indices.empty());
}

TEST(MeshTest, CountsMatchArrayLengths) {
    pluton::Mesh m;
    // 3 vertices, 1 triangle
    m.positions = {0.f, 0.f, 0.f,  1.f, 0.f, 0.f,  0.f, 1.f, 0.f};
    m.normals   = {0.f, 0.f, 1.f,  0.f, 0.f, 1.f,  0.f, 0.f, 1.f};
    m.indices   = {0u, 1u, 2u};

    EXPECT_EQ(m.vertex_count(), 3u);
    EXPECT_EQ(m.triangle_count(), 1u);
}
