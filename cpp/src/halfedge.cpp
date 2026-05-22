#include "pluton/halfedge.h"

#include <algorithm>
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

std::uint32_t HalfEdgeMesh::add_vertex(float x, float y, float z) {
    // Collapse negative zero so -0.0 and 0.0 hash identically.
    if (x == 0.0f) x = 0.0f;
    if (y == 0.0f) y = 0.0f;
    if (z == 0.0f) z = 0.0f;

    const std::uint64_t key = pack_position(x, y, z);
    auto it = position_index_.find(key);
    if (it != position_index_.end() && vertices_[it->second].alive) {
        const auto& p = vertices_[it->second].pos;
        if (p[0] == x && p[1] == y && p[2] == z) {
            return it->second;
        }
        // Hash collision on a different float triple; fall through to allocate.
    }
    const std::uint32_t vid = static_cast<std::uint32_t>(vertices_.size());
    vertices_.push_back(Vertex{{x, y, z}, INVALID_ID, true});
    position_index_[key] = vid;
    dirty_ = true;
    return vid;
}

std::uint32_t HalfEdgeMesh::add_halfedge_pair(std::uint32_t v1_id, std::uint32_t v2_id) {
    if (v1_id == v2_id) {
        throw std::invalid_argument("HalfEdgeMesh::add_halfedge_pair: self-loop at vertex " + std::to_string(v1_id));
    }
    if (!vertex_is_live(v1_id)) {
        throw std::out_of_range("HalfEdgeMesh::add_halfedge_pair: v1_id " + std::to_string(v1_id) + " is not live");
    }
    if (!vertex_is_live(v2_id)) {
        throw std::out_of_range("HalfEdgeMesh::add_halfedge_pair: v2_id " + std::to_string(v2_id) + " is not live");
    }
    const std::uint32_t v_min = std::min(v1_id, v2_id);
    const std::uint32_t v_max = std::max(v1_id, v2_id);
    const std::uint64_t key = pack_pair(v_min, v_max);
    auto it = edge_index_.find(key);
    if (it != edge_index_.end() && edge_is_live(it->second)) {
        return it->second;
    }
    const std::uint32_t he_a = static_cast<std::uint32_t>(halfedges_.size());
    const std::uint32_t he_b = he_a + 1;
    const std::uint32_t edge_id = he_a / 2;
    halfedges_.push_back(HalfEdge{v_min, INVALID_ID, he_b, INVALID_ID, true});
    halfedges_.push_back(HalfEdge{v_max, INVALID_ID, he_a, INVALID_ID, true});
    edge_index_[key] = edge_id;
    dirty_ = true;
    return edge_id;
}

std::uint32_t HalfEdgeMesh::add_face_from_loop(const std::vector<std::uint32_t>& loop,
                                                const std::vector<std::int32_t>& triangles) {
    if (loop.size() < 3) {
        throw std::invalid_argument("HalfEdgeMesh::add_face_from_loop: loop has " + std::to_string(loop.size()) + " vertices; minimum 3");
    }
    for (auto v : loop) {
        if (!vertex_is_live(v)) {
            throw std::out_of_range("HalfEdgeMesh::add_face_from_loop: vertex " + std::to_string(v) + " is not live");
        }
    }
    const std::uint32_t f_id = static_cast<std::uint32_t>(faces_.size());
    Face f{INVALID_ID, {0.0f, 0.0f, 1.0f}, triangles, loop, true};

    // Wire each loop[i] → loop[i+1] half-edge to point to loop[i+1] → loop[i+2].
    // The half-edge from v_from to v_to has origin = v_from. Given the canonical
    // convention (he[2*e].origin = min, he[2*e+1].origin = max), pick the index
    // that matches v_from.
    const std::size_t n = loop.size();
    std::vector<std::uint32_t> loop_halfedges(n, INVALID_ID);
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t v_from = loop[i];
        const std::uint32_t v_to = loop[(i + 1) % n];
        const std::uint32_t v_min = std::min(v_from, v_to);
        const std::uint32_t v_max = std::max(v_from, v_to);
        const std::uint64_t key = pack_pair(v_min, v_max);
        auto it = edge_index_.find(key);
        if (it == edge_index_.end() || !edge_is_live(it->second)) {
            throw std::invalid_argument("HalfEdgeMesh::add_face_from_loop: edge ("
                + std::to_string(v_from) + ", " + std::to_string(v_to) + ") is missing");
        }
        const std::uint32_t edge_id = it->second;
        loop_halfedges[i] = (v_from < v_to) ? (edge_id * 2) : (edge_id * 2 + 1);
    }
    // Wire next pointers + face pointers.
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t he = loop_halfedges[i];
        const std::uint32_t he_next = loop_halfedges[(i + 1) % n];
        halfedges_[he].next = he_next;
        halfedges_[he].face = f_id;
    }
    f.boundary_he = loop_halfedges[0];
    // outgoing_he on each loop vertex points to one of its outgoing half-edges
    // (any will do for now; M3b's adjacency walks pick a starting half-edge).
    for (std::size_t i = 0; i < n; ++i) {
        if (vertices_[loop[i]].outgoing_he == INVALID_ID) {
            vertices_[loop[i]].outgoing_he = loop_halfedges[i];
        }
    }

    faces_.push_back(std::move(f));
    dirty_ = true;
    return f_id;
}

void HalfEdgeMesh::remove_vertex(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_vertex not implemented yet");
}
void HalfEdgeMesh::remove_edge(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_edge not implemented yet");
}
void HalfEdgeMesh::remove_face(std::uint32_t f_id) {
    if (!face_is_live(f_id)) {
        throw std::out_of_range("HalfEdgeMesh::remove_face: face " + std::to_string(f_id) + " is not live");
    }
    // Walk the boundary half-edge cycle and clear face pointers.
    Face& f = faces_[f_id];
    std::uint32_t he = f.boundary_he;
    if (he != INVALID_ID) {
        const std::uint32_t start = he;
        do {
            halfedges_[he].face = INVALID_ID;
            he = halfedges_[he].next;
            if (he == INVALID_ID) break;  // defensive: malformed cycle
        } while (he != start);
    }
    f.alive = false;
    f.boundary_he = INVALID_ID;
    dirty_ = true;
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
