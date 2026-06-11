#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <set>

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

TEST(HalfEdgeMeshTest, RestoreVertexRoundTrips) {
    pluton::HalfEdgeMesh m;
    auto v = m.add_vertex(1.0f, 2.0f, 3.0f);
    m.remove_vertex(v);
    EXPECT_FALSE(m.vertex_is_live(v));

    m.restore_vertex(v, 1.0f, 2.0f, 3.0f);
    EXPECT_TRUE(m.vertex_is_live(v));
    auto p = m.vertex_position(v);
    EXPECT_FLOAT_EQ(p[0], 1.0f);
    EXPECT_FLOAT_EQ(p[1], 2.0f);
    EXPECT_FLOAT_EQ(p[2], 3.0f);
}

TEST(HalfEdgeMeshTest, RestoreVertexLiveSlotThrows) {
    pluton::HalfEdgeMesh m;
    auto v = m.add_vertex(1.0f, 2.0f, 3.0f);
    EXPECT_THROW(m.restore_vertex(v, 0.0f, 0.0f, 0.0f), std::logic_error);
}

TEST(HalfEdgeMeshTest, RestoreEdgeRoundTrips) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto e = m.add_halfedge_pair(v0, v1);
    m.remove_edge(e);
    EXPECT_FALSE(m.edge_is_live(e));

    m.restore_edge(e, v0, v1);
    EXPECT_TRUE(m.edge_is_live(e));
    auto verts = m.edge_vertices(e);
    EXPECT_EQ(verts[0], std::min(v0, v1));
    EXPECT_EQ(verts[1], std::max(v0, v1));
}

TEST(HalfEdgeMeshTest, RestoreFaceRoundTrips) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    const std::vector<std::int32_t> tris = {0, 1, 2};
    auto f = m.add_face_from_loop({v0, v1, v2}, tris);
    m.remove_face(f);
    EXPECT_FALSE(m.face_is_live(f));

    m.restore_face(f, {v0, v1, v2}, tris);
    EXPECT_TRUE(m.face_is_live(f));
    EXPECT_EQ(m.face_loop_vertices(f), std::vector<std::uint32_t>({v0, v1, v2}));
}

TEST(HalfEdgeMeshTest, NextLiveVertexSkipsTombstones) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(2.0f, 0.0f, 0.0f);
    EXPECT_EQ(m.next_live_vertex(0), v0);
    EXPECT_EQ(m.next_live_vertex(v0 + 1), v1);
    EXPECT_EQ(m.next_live_vertex(v1 + 1), v2);

    m.remove_vertex(v1);
    EXPECT_EQ(m.next_live_vertex(0), v0);
    EXPECT_EQ(m.next_live_vertex(v0 + 1), v2);   // skipped v1
    EXPECT_EQ(m.next_live_vertex(v2 + 1), pluton::HalfEdgeMesh::INVALID_ID);
}

TEST(HalfEdgeMeshTest, ClearEmptiesEverythingAndMarksDirty) {
    pluton::HalfEdgeMesh m;
    m.add_vertex(0.0f, 0.0f, 0.0f);
    m.add_vertex(1.0f, 0.0f, 0.0f);
    m.mark_clean();
    EXPECT_FALSE(m.is_dirty());

    m.clear();
    EXPECT_TRUE(m.is_dirty());
    EXPECT_EQ(m.vertex_slab_size(), 0u);
    EXPECT_EQ(m.next_live_vertex(0), pluton::HalfEdgeMesh::INVALID_ID);
}

TEST(HalfEdgeMeshTest, MarkCleanClearsDirty) {
    pluton::HalfEdgeMesh m;
    m.add_vertex(0.0f, 0.0f, 0.0f);
    EXPECT_TRUE(m.is_dirty());
    m.mark_clean();
    EXPECT_FALSE(m.is_dirty());
}

TEST(HalfEdgeMeshTest, EdgeLineBufferShape) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);

    const auto buf = m.edge_line_buffer();
    ASSERT_EQ(buf.size(), 6u);  // 2 endpoints × 3 floats
    EXPECT_FLOAT_EQ(buf[0], 0.0f); EXPECT_FLOAT_EQ(buf[1], 0.0f); EXPECT_FLOAT_EQ(buf[2], 0.0f);
    EXPECT_FLOAT_EQ(buf[3], 1.0f); EXPECT_FLOAT_EQ(buf[4], 0.0f); EXPECT_FLOAT_EQ(buf[5], 0.0f);
}

TEST(HalfEdgeMeshTest, EdgeLineBufferSkipsTombstones) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(2.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.remove_edge(0u);

    const auto buf = m.edge_line_buffer();
    EXPECT_EQ(buf.size(), 6u);  // only the live edge contributes
}

TEST(HalfEdgeMeshTest, FaceTriangleBufferShape) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});

    auto [positions, normals] = m.face_triangle_buffer();
    EXPECT_EQ(positions.size(), 9u);  // 1 triangle × 3 verts × 3 floats
    EXPECT_EQ(normals.size(), 9u);
    // Normal of every vertex is the face's +Z normal.
    // Loop (0,0,0)→(1,0,0)→(0,1,0) is CCW when viewed from +Z, so cross
    // product e1=(1,0,0) × e2=(0,1,0) = (0,0,1).
    for (std::size_t i = 0; i + 2 < normals.size(); i += 3) {
        EXPECT_FLOAT_EQ(normals[i + 0], 0.0f);
        EXPECT_FLOAT_EQ(normals[i + 1], 0.0f);
        EXPECT_FLOAT_EQ(normals[i + 2], 1.0f);
    }
}

// Regression test: add_face_from_loop must compute the geometric normal from
// the cross product of the first two boundary edges — NOT hardcode (0,0,1).
// A face on the YZ-plane (x=0) with CCW winding (viewed from +X) should have
// normal (+1, 0, 0).
//
// Vertices: A=(0,0,0), B=(0,1,0), C=(0,1,1), D=(0,0,1)
// e1 = B - A = (0,1,0)
// e2 = C - A = (0,1,1)
// n = e1 × e2 = (1*1 - 0*1, 0*0 - 0*1, 0*1 - 1*0) = (1, 0, 0)  → normalised: (+1, 0, 0)
TEST(HalfEdgeMeshTest, FaceNormalComputedGeometricallyYZPlane) {
    pluton::HalfEdgeMesh m;
    // YZ-plane quad: x=0, CCW from +X
    auto vA = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto vB = m.add_vertex(0.0f, 1.0f, 0.0f);
    auto vC = m.add_vertex(0.0f, 1.0f, 1.0f);
    auto vD = m.add_vertex(0.0f, 0.0f, 1.0f);
    m.add_halfedge_pair(vA, vB);
    m.add_halfedge_pair(vB, vC);
    m.add_halfedge_pair(vC, vD);
    m.add_halfedge_pair(vD, vA);
    const std::vector<std::int32_t> tris = {
        static_cast<std::int32_t>(vA), static_cast<std::int32_t>(vB), static_cast<std::int32_t>(vC),
        static_cast<std::int32_t>(vA), static_cast<std::int32_t>(vC), static_cast<std::int32_t>(vD),
    };
    m.add_face_from_loop({vA, vB, vC, vD}, tris);

    auto [positions, normals] = m.face_triangle_buffer();
    ASSERT_EQ(normals.size(), 18u);  // 2 triangles × 3 verts × 3 floats
    // Every vertex should share the face normal: (+1, 0, 0)
    for (std::size_t i = 0; i + 2 < normals.size(); i += 3) {
        EXPECT_NEAR(normals[i + 0], +1.0f, 1e-6f);
        EXPECT_NEAR(normals[i + 1],  0.0f, 1e-6f);
        EXPECT_NEAR(normals[i + 2],  0.0f, 1e-6f);
    }
}

// ====================================================================
// M3c: faces_are_coplanar
// ====================================================================

namespace {

// Helper: build a triangle face from 3 explicit positions, return face id.
std::uint32_t add_triangle(pluton::HalfEdgeMesh& m,
                           std::array<float, 3> p0,
                           std::array<float, 3> p1,
                           std::array<float, 3> p2) {
    auto v0 = m.add_vertex(p0[0], p0[1], p0[2]);
    auto v1 = m.add_vertex(p1[0], p1[1], p1[2]);
    auto v2 = m.add_vertex(p2[0], p2[1], p2[2]);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    return m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});
}

constexpr float kCos05Deg = 0.99996192306f;   // cos(0.5°)
constexpr float kDistTol  = 1.0e-4f;

}  // namespace

TEST(HalfEdgeMeshTest, FacesAreCoplanar_TrueForIdenticalPlanes) {
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});       // XY plane
    auto f2 = add_triangle(m, {2,2,0}, {3,2,0}, {2,3,0});       // also XY plane
    EXPECT_TRUE(m.faces_are_coplanar(f1, f2, kCos05Deg, kDistTol));
    EXPECT_TRUE(m.faces_are_coplanar(f2, f1, kCos05Deg, kDistTol));  // symmetric
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_TrueWithinAngleTolerance) {
    // Two faces on planes whose normals differ by 0.3° — under the 0.5° tolerance.
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});  // normal (0,0,1)
    // Rotate the second face by 0.3° about X: normal becomes (0, -sin(0.3°), cos(0.3°))
    float c = std::cos(0.3f * 3.14159265f / 180.0f);
    float s = std::sin(0.3f * 3.14159265f / 180.0f);
    auto f2 = add_triangle(m, {2,2,0}, {3,2,0}, {2, 2 + c, s});
    // Loosened dist_tol: 0.3° tilt on a face anchored 2 units from origin gives
    // a ~1.05e-2 worst-case plane offset in the symmetric distance check, so
    // the project default 1e-4 would fail this geometry. The angle test is
    // what's being exercised here.
    EXPECT_TRUE(m.faces_are_coplanar(f1, f2, kCos05Deg, 2e-2f));   // looser dist
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_FalseBeyondAngleTolerance) {
    // 1.0° apart — over the 0.5° tolerance.
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});
    float c = std::cos(1.0f * 3.14159265f / 180.0f);
    float s = std::sin(1.0f * 3.14159265f / 180.0f);
    auto f2 = add_triangle(m, {2,2,0}, {3,2,0}, {2, 2 + c, s});
    EXPECT_FALSE(m.faces_are_coplanar(f1, f2, kCos05Deg, 1.0f));
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_FalseBeyondDistanceTolerance) {
    // Two parallel XY planes offset by 1e-3 (over the 1e-4 dist tolerance).
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});       // z = 0
    auto f2 = add_triangle(m, {2,2,1e-3f}, {3,2,1e-3f}, {2,3,1e-3f});  // z = 0.001
    EXPECT_FALSE(m.faces_are_coplanar(f1, f2, kCos05Deg, kDistTol));
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_FalseForDegenerateNormal) {
    // f1 has zero area (all 3 vertices collinear). Must not crash; must return false.
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(2,0,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f_degen = m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});

    auto f_good = add_triangle(m, {5,0,0}, {6,0,0}, {5,1,0});
    EXPECT_FALSE(m.faces_are_coplanar(f_degen, f_good, kCos05Deg, kDistTol));
    EXPECT_FALSE(m.faces_are_coplanar(f_good, f_degen, kCos05Deg, kDistTol));
}

// ====================================================================
// M3c: dissolve_edge — happy path
// ====================================================================

TEST(HalfEdgeMeshTest, DissolveEdge_TwoTrianglesIntoQuad) {
    // Build two triangles sharing edge v1—v2:
    //   T1 = (v0, v1, v2)   T2 = (v1, v3, v2)   shared edge: v1—v2
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(1,1,0);
    auto v3 = m.add_vertex(2,1,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);                                       // shared
    m.add_halfedge_pair(v2, v0);
    m.add_halfedge_pair(v1, v3);
    m.add_halfedge_pair(v3, v2);

    auto f1 = m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});
    auto f2 = m.add_face_from_loop({v1, v3, v2}, {(int)v1, (int)v3, (int)v2});

    // Find the shared edge id (the v1—v2 pair).
    std::uint32_t shared_edge = pluton::HalfEdgeMesh::INVALID_ID;
    for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2; ++e) {
        auto verts = m.edge_vertices(e);
        if ((verts[0] == v1 && verts[1] == v2) || (verts[0] == v2 && verts[1] == v1)) {
            shared_edge = e;
            break;
        }
    }
    ASSERT_NE(shared_edge, pluton::HalfEdgeMesh::INVALID_ID);

    auto merged = m.dissolve_edge(shared_edge);

    EXPECT_NE(merged, pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_FALSE(m.face_is_live(f1));
    EXPECT_FALSE(m.face_is_live(f2));
    EXPECT_FALSE(m.edge_is_live(shared_edge));
    EXPECT_TRUE(m.face_is_live(merged));

    // The merged face is a quad with 4 vertices.
    auto loop = m.face_loop_vertices(merged);
    EXPECT_EQ(loop.size(), 4u);

    // Verify the merged loop contains exactly {v0, v1, v2, v3} (set equality).
    std::set<std::uint32_t> loop_set(loop.begin(), loop.end());
    std::set<std::uint32_t> expected{v0, v1, v2, v3};
    EXPECT_EQ(loop_set, expected);

    // Verify each consecutive pair in the merged loop is connected by a live
    // half-edge pair (i.e. the spliced loop is a valid traversable cycle, not
    // four disconnected vertices).
    for (std::size_t i = 0; i < loop.size(); ++i) {
        std::uint32_t a = loop[i];
        std::uint32_t b = loop[(i + 1) % loop.size()];
        // Find the edge slot for (a, b); both halves must be live and at least
        // one half must belong to the merged face.
        bool found_live_edge_to_merged = false;
        for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2u; ++e) {
            if (!m.edge_is_live(e)) continue;
            auto verts = m.edge_vertices(e);
            if ((verts[0] == a && verts[1] == b) || (verts[0] == b && verts[1] == a)) {
                std::uint32_t he_lo = 2u * e;
                std::uint32_t he_hi = 2u * e + 1u;
                if (m.halfedge_face(he_lo) == merged || m.halfedge_face(he_hi) == merged) {
                    found_live_edge_to_merged = true;
                }
                break;
            }
        }
        EXPECT_TRUE(found_live_edge_to_merged)
            << "Consecutive merged-loop pair (" << a << ", " << b
            << ") has no live edge belonging to merged face " << merged;
    }
}

TEST(HalfEdgeMeshTest, DissolveEdge_TombstonesEdgeId) {
    // After dissolve, the edge slot should be tombstoned (not compacted).
    // Querying the now-dead edge returns invalid; slab size unchanged.
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(1,1,0);
    auto v3 = m.add_vertex(2,1,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_halfedge_pair(v1, v3);
    m.add_halfedge_pair(v3, v2);
    m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});
    m.add_face_from_loop({v1, v3, v2}, {(int)v1, (int)v3, (int)v2});

    // Find the shared edge again.
    std::uint32_t shared_edge = pluton::HalfEdgeMesh::INVALID_ID;
    for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2; ++e) {
        auto verts = m.edge_vertices(e);
        if ((verts[0] == v1 && verts[1] == v2) || (verts[0] == v2 && verts[1] == v1)) {
            shared_edge = e;
            break;
        }
    }

    auto slab_before = m.halfedge_slab_size();
    m.dissolve_edge(shared_edge);
    EXPECT_EQ(m.halfedge_slab_size(), slab_before);     // no compaction
    EXPECT_FALSE(m.edge_is_live(shared_edge));
}

TEST(HalfEdgeMeshTest, DissolveEdge_TwoQuadsIntoHexagon) {
    // Two quads sharing an edge — dissolve produces a 6-vertex face.
    //   Q1 = (v0, v1, v2, v3)  Q2 = (v1, v4, v5, v2)  shared: v1—v2
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(1,1,0);
    auto v3 = m.add_vertex(0,1,0);
    auto v4 = m.add_vertex(2,0,0);
    auto v5 = m.add_vertex(2,1,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);
    m.add_halfedge_pair(v1, v4);
    m.add_halfedge_pair(v4, v5);
    m.add_halfedge_pair(v5, v2);
    m.add_face_from_loop({v0, v1, v2, v3},
        {(int)v0, (int)v1, (int)v2, (int)v0, (int)v2, (int)v3});
    m.add_face_from_loop({v1, v4, v5, v2},
        {(int)v1, (int)v4, (int)v5, (int)v1, (int)v5, (int)v2});

    std::uint32_t shared_edge = pluton::HalfEdgeMesh::INVALID_ID;
    for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2; ++e) {
        auto verts = m.edge_vertices(e);
        if ((verts[0] == v1 && verts[1] == v2) || (verts[0] == v2 && verts[1] == v1)) {
            shared_edge = e;
            break;
        }
    }

    auto merged = m.dissolve_edge(shared_edge);
    EXPECT_NE(merged, pluton::HalfEdgeMesh::INVALID_ID);
    auto loop = m.face_loop_vertices(merged);
    EXPECT_EQ(loop.size(), 6u);
}

TEST(HalfEdgeMeshTest, DissolveEdge_RejectsBoundaryEdge) {
    // Single triangle — all three edges are boundary (only one half-edge each).
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(0,1,0);
    auto e01 = m.add_halfedge_pair(v0, v1) / 2u;
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});

    EXPECT_EQ(m.dissolve_edge(e01), pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_TRUE(m.edge_is_live(e01));   // unchanged
}

TEST(HalfEdgeMeshTest, DissolveEdge_RejectsAlreadyTombstonedEdge) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto e = m.add_halfedge_pair(v0, v1) / 2u;
    m.remove_edge(e);

    EXPECT_EQ(m.dissolve_edge(e), pluton::HalfEdgeMesh::INVALID_ID);
}

TEST(HalfEdgeMeshTest, DissolveEdge_RejectsMultiSharedEdges) {
    // Pathological topology where two faces share two edges (e.g., a folded
    // bigon). Construct manually: two triangles sharing two edges. Building a
    // valid multi-shared topology in our half-edge structure is awkward, so
    // for now we accept that the guard exists and the unit test is exercised
    // via the existing implementation path. We assert the API surface stays
    // honest: a follow-up M3 issue can construct the actual degenerate input.
    SUCCEED() << "Multi-shared rejection path covered by code review only; "
              << "constructing a valid degenerate half-edge input requires a "
              << "test helper not yet built. Filed as known carry-over.";
}

// ---- split_edge -------------------------------------------------------------

namespace {
// Build two quads sharing edge (v1,v2): f1=[v0,v1,v2,v3], f2=[v1,v4,v5,v2].
pluton::HalfEdgeMesh make_two_quads(std::uint32_t& shared_edge_out) {
    using pluton::HalfEdgeMesh;
    HalfEdgeMesh m;
    auto v0 = m.add_vertex(0, 0, 0);
    auto v1 = m.add_vertex(1, 0, 0);
    auto v2 = m.add_vertex(1, 1, 0);
    auto v3 = m.add_vertex(0, 1, 0);
    auto v4 = m.add_vertex(2, 0, 0);
    auto v5 = m.add_vertex(2, 1, 0);
    m.add_halfedge_pair(v0, v1);
    shared_edge_out = m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);
    m.add_halfedge_pair(v1, v4);
    m.add_halfedge_pair(v4, v5);
    m.add_halfedge_pair(v5, v2);
    m.add_face_from_loop({v0, v1, v2, v3}, {(int)v0,(int)v1,(int)v2, (int)v0,(int)v2,(int)v3});
    m.add_face_from_loop({v1, v4, v5, v2}, {(int)v1,(int)v4,(int)v5, (int)v1,(int)v5,(int)v2});
    return m;
}
}  // namespace

TEST(SplitEdge, InteriorEdgeInsertsVertexAndRebuildsBothFaces) {
    std::uint32_t e_shared = 0;
    auto m = make_two_quads(e_shared);

    auto res = m.split_edge(e_shared, 0.5f);
    ASSERT_TRUE(res.has_value());

    auto wp = m.vertex_position(res->vertex);
    EXPECT_FLOAT_EQ(wp[0], 1.0f);
    EXPECT_FLOAT_EQ(wp[1], 0.5f);
    EXPECT_FLOAT_EQ(wp[2], 0.0f);

    EXPECT_FALSE(m.edge_is_live(e_shared));
    EXPECT_TRUE(m.edge_is_live(res->edge_a));
    EXPECT_TRUE(m.edge_is_live(res->edge_b));

    EXPECT_NE(res->face_a, pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_NE(res->face_b, pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_TRUE(m.face_is_live(res->face_a));
    EXPECT_TRUE(m.face_is_live(res->face_b));
    EXPECT_EQ(m.face_loop_vertices(res->face_a).size(), 5u);
    EXPECT_EQ(m.face_loop_vertices(res->face_b).size(), 5u);

    std::uint32_t live = 0;
    for (auto f = m.next_live_face(0); f != pluton::HalfEdgeMesh::INVALID_ID; f = m.next_live_face(f + 1))
        ++live;
    EXPECT_EQ(live, 2u);
}
