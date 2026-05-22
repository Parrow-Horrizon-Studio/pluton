#include "pluton/halfedge.h"

#include <cstring>

namespace pluton {

// --- Static helpers ----------------------------------------------------

std::uint64_t HalfEdgeMesh::pack_position(float x, float y, float z) noexcept {
    // We need a stable 64-bit hash key derived from the three float32 bits.
    // FNV-1a over the 12 bytes is good enough for dedup; collisions are
    // tolerable because we compare positions on collision (see add_vertex).
    std::uint32_t bx, by, bz;
    std::memcpy(&bx, &x, 4);
    std::memcpy(&by, &y, 4);
    std::memcpy(&bz, &z, 4);
    std::uint64_t h = 0xcbf29ce484222325ull;
    for (std::uint32_t b : {bx, by, bz}) {
        for (int i = 0; i < 4; ++i) {
            h ^= static_cast<std::uint64_t>((b >> (i * 8)) & 0xFFu);
            h *= 0x100000001b3ull;
        }
    }
    return h;
}

std::uint64_t HalfEdgeMesh::pack_pair(std::uint32_t a, std::uint32_t b) noexcept {
    return (static_cast<std::uint64_t>(a) << 32) | static_cast<std::uint64_t>(b);
}

// --- Stubs for Task 2+ -------------------------------------------------

std::uint32_t HalfEdgeMesh::add_vertex(float, float, float) {
    throw std::runtime_error("HalfEdgeMesh::add_vertex not implemented yet");
}

std::uint32_t HalfEdgeMesh::add_halfedge_pair(std::uint32_t, std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::add_halfedge_pair not implemented yet");
}

std::uint32_t HalfEdgeMesh::add_face_from_loop(const std::vector<std::uint32_t>&,
                                                const std::vector<std::int32_t>&) {
    throw std::runtime_error("HalfEdgeMesh::add_face_from_loop not implemented yet");
}

void HalfEdgeMesh::remove_vertex(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_vertex not implemented yet");
}
void HalfEdgeMesh::remove_edge(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_edge not implemented yet");
}
void HalfEdgeMesh::remove_face(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_face not implemented yet");
}

void HalfEdgeMesh::restore_vertex(std::uint32_t, float, float, float) {
    throw std::runtime_error("HalfEdgeMesh::restore_vertex not implemented yet");
}
void HalfEdgeMesh::restore_edge(std::uint32_t, std::uint32_t, std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::restore_edge not implemented yet");
}
void HalfEdgeMesh::restore_face(std::uint32_t,
                                 const std::vector<std::uint32_t>&,
                                 const std::vector<std::int32_t>&) {
    throw std::runtime_error("HalfEdgeMesh::restore_face not implemented yet");
}

void HalfEdgeMesh::clear() noexcept {
    vertices_.clear();
    halfedges_.clear();
    faces_.clear();
    position_index_.clear();
    edge_index_.clear();
    dirty_ = true;
}

bool HalfEdgeMesh::vertex_is_live(std::uint32_t v_id) const noexcept {
    return v_id < vertices_.size() && vertices_[v_id].alive;
}
bool HalfEdgeMesh::edge_is_live(std::uint32_t e_id) const noexcept {
    const std::uint32_t he = e_id * 2;
    return he < halfedges_.size() && halfedges_[he].alive;
}
bool HalfEdgeMesh::face_is_live(std::uint32_t f_id) const noexcept {
    return f_id < faces_.size() && faces_[f_id].alive;
}

std::array<float, 3> HalfEdgeMesh::vertex_position(std::uint32_t v_id) const {
    if (!vertex_is_live(v_id)) {
        throw std::out_of_range("HalfEdgeMesh::vertex_position: vertex " + std::to_string(v_id) + " is not live");
    }
    const auto& v = vertices_[v_id];
    return {v.pos[0], v.pos[1], v.pos[2]};
}

std::array<std::uint32_t, 2> HalfEdgeMesh::edge_vertices(std::uint32_t e_id) const {
    if (!edge_is_live(e_id)) {
        throw std::out_of_range("HalfEdgeMesh::edge_vertices: edge " + std::to_string(e_id) + " is not live");
    }
    const std::uint32_t he_a = e_id * 2;
    const std::uint32_t he_b = he_a + 1;
    return {halfedges_[he_a].origin, halfedges_[he_b].origin};
}

std::vector<std::uint32_t> HalfEdgeMesh::face_loop_vertices(std::uint32_t f_id) const {
    if (!face_is_live(f_id)) {
        throw std::out_of_range("HalfEdgeMesh::face_loop_vertices: face " + std::to_string(f_id) + " is not live");
    }
    return faces_[f_id].loop;
}

std::vector<std::int32_t> HalfEdgeMesh::face_triangles(std::uint32_t f_id) const {
    if (!face_is_live(f_id)) {
        throw std::out_of_range("HalfEdgeMesh::face_triangles: face " + std::to_string(f_id) + " is not live");
    }
    return faces_[f_id].tris;
}

std::uint32_t HalfEdgeMesh::halfedge_origin(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].origin : INVALID_ID;
}
std::uint32_t HalfEdgeMesh::halfedge_next(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].next : INVALID_ID;
}
std::uint32_t HalfEdgeMesh::halfedge_twin(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].twin : INVALID_ID;
}
std::uint32_t HalfEdgeMesh::halfedge_face(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].face : INVALID_ID;
}

std::uint32_t HalfEdgeMesh::next_live_vertex(std::uint32_t start) const noexcept {
    for (std::uint32_t i = start; i < vertices_.size(); ++i) {
        if (vertices_[i].alive) return i;
    }
    return INVALID_ID;
}
std::uint32_t HalfEdgeMesh::next_live_edge(std::uint32_t start) const noexcept {
    for (std::uint32_t i = start; (i * 2) < halfedges_.size(); ++i) {
        if (halfedges_[i * 2].alive) return i;
    }
    return INVALID_ID;
}
std::uint32_t HalfEdgeMesh::next_live_face(std::uint32_t start) const noexcept {
    for (std::uint32_t i = start; i < faces_.size(); ++i) {
        if (faces_[i].alive) return i;
    }
    return INVALID_ID;
}

std::vector<float> HalfEdgeMesh::edge_line_buffer() const {
    std::vector<float> out;
    for (std::uint32_t e = next_live_edge(0); e != INVALID_ID; e = next_live_edge(e + 1)) {
        const std::uint32_t he_a = e * 2;
        const std::uint32_t va = halfedges_[he_a].origin;
        const std::uint32_t vb = halfedges_[he_a + 1].origin;
        const auto& pa = vertices_[va].pos;
        const auto& pb = vertices_[vb].pos;
        out.insert(out.end(), {pa[0], pa[1], pa[2], pb[0], pb[1], pb[2]});
    }
    return out;
}

std::pair<std::vector<float>, std::vector<float>> HalfEdgeMesh::face_triangle_buffer() const {
    std::vector<float> positions;
    std::vector<float> normals;
    for (std::uint32_t f = next_live_face(0); f != INVALID_ID; f = next_live_face(f + 1)) {
        const auto& face = faces_[f];
        for (std::size_t i = 0; i + 2 < face.tris.size(); i += 3) {
            for (std::size_t k = 0; k < 3; ++k) {
                const std::uint32_t v = static_cast<std::uint32_t>(face.tris[i + k]);
                const auto& p = vertices_[v].pos;
                positions.insert(positions.end(), {p[0], p[1], p[2]});
                normals.insert(normals.end(), {face.normal[0], face.normal[1], face.normal[2]});
            }
        }
    }
    return {std::move(positions), std::move(normals)};
}

}  // namespace pluton
