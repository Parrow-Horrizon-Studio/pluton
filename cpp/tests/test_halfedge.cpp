#include <gtest/gtest.h>

#include "pluton/halfedge.h"

TEST(HalfEdgeMeshTest, DefaultConstructedIsEmpty) {
    pluton::HalfEdgeMesh m;
    EXPECT_EQ(m.vertex_slab_size(), 0u);
    EXPECT_EQ(m.halfedge_slab_size(), 0u);
    EXPECT_EQ(m.face_slab_size(), 0u);
    EXPECT_FALSE(m.is_dirty());
}

TEST(HalfEdgeMeshTest, ClearSetsDirty) {
    pluton::HalfEdgeMesh m;
    m.clear();
    EXPECT_TRUE(m.is_dirty());
    EXPECT_EQ(m.vertex_slab_size(), 0u);
}

TEST(HalfEdgeMeshTest, InvalidIdConstant) {
    EXPECT_EQ(pluton::HalfEdgeMesh::INVALID_ID, 0xFFFFFFFFu);
}
