#pragma once

#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace pluton {

/// Half-edge mesh — the topology source of truth for Pluton's M3+ kernel.
///
/// Storage layout:
///   - Vertices, half-edges, and faces live in std::vector slabs.
///   - Each entity has a stable uint32_t ID = its index in the slab.
///   - Removal sets `alive = false` (tombstone). Slots are never reused;
///     IDs stay valid for resurrection by restore_*.
///   - Edges are implicit: every "edge" is a pair of twin half-edges at
///     adjacent vector indices (2*edge_id and 2*edge_id+1). The half-edge
///     at the even index has origin = min(v1, v2); the odd one has
///     origin = max(v1, v2).
class HalfEdgeMesh {
public:
    static constexpr std::uint32_t INVALID_ID = 0xFFFFFFFFu;

    // ---- Mutators ----------------------------------------------------
    std::uint32_t add_vertex(float x, float y, float z);
    std::uint32_t add_halfedge_pair(std::uint32_t v1_id, std::uint32_t v2_id);
    std::uint32_t add_face_from_loop(const std::vector<std::uint32_t>& loop,
                                     const std::vector<std::int32_t>& triangles);

    void remove_vertex(std::uint32_t v_id);
    void remove_edge(std::uint32_t e_id);
    void remove_face(std::uint32_t f_id);

    void restore_vertex(std::uint32_t v_id, float x, float y, float z);
    void restore_edge(std::uint32_t e_id, std::uint32_t v1_id, std::uint32_t v2_id);
    void restore_face(std::uint32_t f_id,
                      const std::vector<std::uint32_t>& loop,
                      const std::vector<std::int32_t>& triangles);

    void clear() noexcept;

    // ---- Queries -----------------------------------------------------
    bool vertex_is_live(std::uint32_t v_id) const noexcept;
    bool edge_is_live(std::uint32_t e_id) const noexcept;
    bool face_is_live(std::uint32_t f_id) const noexcept;

    std::array<float, 3> vertex_position(std::uint32_t v_id) const;
    std::array<std::uint32_t, 2> edge_vertices(std::uint32_t e_id) const;
    std::vector<std::uint32_t> face_loop_vertices(std::uint32_t f_id) const;
    std::vector<std::int32_t> face_triangles(std::uint32_t f_id) const;

    /// Robust planar-coplanarity test for two faces.
    /// Returns true iff both:
    ///   - the angle between unit normals satisfies dot(n1, n2) > angle_tol_cos, AND
    ///   - every vertex of either face lies within `dist_tol` of the other face's plane.
    /// Returns false (without crashing) for degenerate-normal faces (|n| < 1e-7).
    /// Project defaults: angle_tol_cos = cos(0.5°) ≈ 0.9999619f, dist_tol = 1e-4f.
    bool faces_are_coplanar(std::uint32_t f1_id,
                            std::uint32_t f2_id,
                            float angle_tol_cos,
                            float dist_tol) const;

    std::uint32_t halfedge_origin(std::uint32_t he_id) const noexcept;
    std::uint32_t halfedge_next(std::uint32_t he_id) const noexcept;
    std::uint32_t halfedge_twin(std::uint32_t he_id) const noexcept;
    std::uint32_t halfedge_face(std::uint32_t he_id) const noexcept;

    std::uint32_t next_live_vertex(std::uint32_t start = 0) const noexcept;
    std::uint32_t next_live_edge(std::uint32_t start = 0) const noexcept;
    std::uint32_t next_live_face(std::uint32_t start = 0) const noexcept;

    std::vector<float> edge_line_buffer() const;
    std::pair<std::vector<float>, std::vector<float>> face_triangle_buffer() const;

    bool is_dirty() const noexcept { return dirty_; }
    void mark_clean() noexcept { dirty_ = false; }

    std::size_t vertex_slab_size() const noexcept { return vertices_.size(); }
    std::size_t halfedge_slab_size() const noexcept { return halfedges_.size(); }
    std::size_t face_slab_size() const noexcept { return faces_.size(); }

private:
    struct Vertex   { float pos[3]; std::uint32_t outgoing_he; bool alive; };
    struct HalfEdge { std::uint32_t origin; std::uint32_t next; std::uint32_t twin; std::uint32_t face; bool alive; };
    struct Face     { std::uint32_t boundary_he; float normal[3]; std::vector<std::int32_t> tris; std::vector<std::uint32_t> loop; bool alive; };

    std::vector<Vertex>   vertices_;
    std::vector<HalfEdge> halfedges_;
    std::vector<Face>     faces_;

    // Packed position → live vertex id, for idempotent add_vertex.
    std::unordered_map<std::uint64_t, std::uint32_t> position_index_;
    // (min, max) vertex pair → edge id, for idempotent add_halfedge_pair.
    std::unordered_map<std::uint64_t, std::uint32_t> edge_index_;

    bool dirty_ = false;

    // Helpers
    static std::uint64_t pack_position(float x, float y, float z) noexcept;
    static std::uint64_t pack_pair(std::uint32_t a, std::uint32_t b) noexcept;
};

}  // namespace pluton
