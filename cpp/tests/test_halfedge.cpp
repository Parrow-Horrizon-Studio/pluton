#include <gtest/gtest.h>

#include <algorithm>

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

TEST(HalfEdgeMeshTest, AddVertexReturnsNewIds) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    EXPECT_NE(v0, v1);
    EXPECT_TRUE(m.vertex_is_live(v0));
    EXPECT_TRUE(m.vertex_is_live(v1));
    EXPECT_TRUE(m.is_dirty());
}

TEST(HalfEdgeMeshTest, AddVertexIsIdempotentOnExactMatch) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(2.0f, 3.0f, 0.0f);
    auto v1 = m.add_vertex(2.0f, 3.0f, 0.0f);
    EXPECT_EQ(v0, v1);
    EXPECT_EQ(m.vertex_slab_size(), 1u);
}

TEST(HalfEdgeMeshTest, AddVertexCollapsesNegativeZero) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(-0.0f, 0.0f, 0.0f);
    EXPECT_EQ(v0, v1);
}

TEST(HalfEdgeMeshTest, AddVertexStoresPosition) {
    pluton::HalfEdgeMesh m;
    auto v = m.add_vertex(5.0f, 6.0f, 7.0f);
    auto p = m.vertex_position(v);
    EXPECT_FLOAT_EQ(p[0], 5.0f);
    EXPECT_FLOAT_EQ(p[1], 6.0f);
    EXPECT_FLOAT_EQ(p[2], 7.0f);
}

TEST(HalfEdgeMeshTest, AddHalfedgePairReturnsEdgeId) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto e = m.add_halfedge_pair(v0, v1);
    EXPECT_EQ(e, 0u);
    EXPECT_TRUE(m.edge_is_live(e));
    EXPECT_EQ(m.halfedge_slab_size(), 2u);  // exactly one pair allocated
}

TEST(HalfEdgeMeshTest, AddHalfedgePairIsIdempotentUnordered) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto a = m.add_halfedge_pair(v0, v1);
    auto b = m.add_halfedge_pair(v1, v0);
    EXPECT_EQ(a, b);
    EXPECT_EQ(m.halfedge_slab_size(), 2u);
}

TEST(HalfEdgeMeshTest, AddHalfedgePairRejectsSelfLoop) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    EXPECT_THROW(m.add_halfedge_pair(v0, v0), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, AddHalfedgePairWiresTwinsAndOrigins) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto e = m.add_halfedge_pair(v1, v0);  // swapped order on input

    const auto verts = m.edge_vertices(e);
    EXPECT_EQ(verts[0], std::min(v0, v1));   // canonical: v1 < v2
    EXPECT_EQ(verts[1], std::max(v0, v1));

    const std::uint32_t he_a = e * 2;
    const std::uint32_t he_b = he_a + 1;
    EXPECT_EQ(m.halfedge_twin(he_a), he_b);
    EXPECT_EQ(m.halfedge_twin(he_b), he_a);
    EXPECT_EQ(m.halfedge_origin(he_a), std::min(v0, v1));
    EXPECT_EQ(m.halfedge_origin(he_b), std::max(v0, v1));
    EXPECT_EQ(m.halfedge_face(he_a), pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_EQ(m.halfedge_face(he_b), pluton::HalfEdgeMesh::INVALID_ID);
}
