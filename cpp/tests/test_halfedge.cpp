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

TEST(HalfEdgeMeshTest, AddFaceFromLoopWiresBoundaryCycle) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(1.0f, 1.0f, 0.0f);
    auto v3 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);

    const std::vector<std::uint32_t> loop = {v0, v1, v2, v3};
    const std::vector<std::int32_t> tris = {static_cast<std::int32_t>(v0), static_cast<std::int32_t>(v1), static_cast<std::int32_t>(v2),
                                            static_cast<std::int32_t>(v0), static_cast<std::int32_t>(v2), static_cast<std::int32_t>(v3)};
    auto f = m.add_face_from_loop(loop, tris);
    EXPECT_EQ(f, 0u);
    EXPECT_TRUE(m.face_is_live(f));
    EXPECT_EQ(m.face_loop_vertices(f), loop);
    EXPECT_EQ(m.face_triangles(f), tris);
}

TEST(HalfEdgeMeshTest, AddFaceFromLoopRejectsShortLoop) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    EXPECT_THROW(m.add_face_from_loop({v0, v1}, {}), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, AddFaceFromLoopSetsHalfedgeFacePointers) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    const std::vector<std::int32_t> tris = {static_cast<std::int32_t>(v0),
                                            static_cast<std::int32_t>(v1),
                                            static_cast<std::int32_t>(v2)};
    auto f = m.add_face_from_loop({v0, v1, v2}, tris);

    // For each edge in the loop, exactly ONE of the two halfedges should have
    // its face set to f (the one walking the loop in order). The twin should
    // stay at INVALID_ID (it's a boundary edge).
    for (std::uint32_t e = 0; e < 3; ++e) {
        const std::uint32_t he_a = e * 2;
        const std::uint32_t he_b = he_a + 1;
        EXPECT_TRUE(m.halfedge_face(he_a) == f || m.halfedge_face(he_b) == f);
        EXPECT_TRUE(m.halfedge_face(he_a) == pluton::HalfEdgeMesh::INVALID_ID || m.halfedge_face(he_b) == pluton::HalfEdgeMesh::INVALID_ID);
    }
}

TEST(HalfEdgeMeshTest, RemoveFaceTombstonesSlot) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f = m.add_face_from_loop({v0, v1, v2}, {static_cast<std::int32_t>(v0), static_cast<std::int32_t>(v1), static_cast<std::int32_t>(v2)});
    EXPECT_TRUE(m.face_is_live(f));

    m.remove_face(f);
    EXPECT_FALSE(m.face_is_live(f));

    // Vertices and edges stay alive.
    EXPECT_TRUE(m.vertex_is_live(v0));
    EXPECT_TRUE(m.edge_is_live(0u));
}

TEST(HalfEdgeMeshTest, RemoveFaceClearsHalfedgeFacePointers) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f = m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});

    m.remove_face(f);
    for (std::uint32_t he = 0; he < m.halfedge_slab_size(); ++he) {
        EXPECT_EQ(m.halfedge_face(he), pluton::HalfEdgeMesh::INVALID_ID);
    }
}

TEST(HalfEdgeMeshTest, RemoveFaceAlreadyDeadThrows) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f = m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});
    m.remove_face(f);
    EXPECT_THROW(m.remove_face(f), std::out_of_range);
}

TEST(HalfEdgeMeshTest, RemoveEdgeRejectsIfFaceUsesIt) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});
    EXPECT_THROW(m.remove_edge(0u), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, RemoveEdgeAfterFaceWorks) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.remove_edge(0u);
    EXPECT_FALSE(m.edge_is_live(0u));
}

TEST(HalfEdgeMeshTest, RemoveEdgeAlreadyDeadThrows) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.remove_edge(0u);
    EXPECT_THROW(m.remove_edge(0u), std::out_of_range);
}

TEST(HalfEdgeMeshTest, RemoveVertexRejectsIfEdgeUsesIt) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    EXPECT_THROW(m.remove_vertex(v0), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, RemoveVertexAfterEdgeWorks) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.remove_edge(0u);
    m.remove_vertex(v0);
    EXPECT_FALSE(m.vertex_is_live(v0));
    EXPECT_TRUE(m.vertex_is_live(v1));
}
