#include "pluton/halfedge.h"

#include <algorithm>
#include <cmath>
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
    // Compute geometric normal from the first three boundary vertices.
    // Assumes planar face — M2/M3a only produce planar faces; M4+ will revisit.
    const auto& p0 = vertices_[loop[0]].pos;
    const auto& p1 = vertices_[loop[1]].pos;
    const auto& p2 = vertices_[loop[2]].pos;
    const float e1x = p1[0] - p0[0];
    const float e1y = p1[1] - p0[1];
    const float e1z = p1[2] - p0[2];
    const float e2x = p2[0] - p0[0];
    const float e2y = p2[1] - p0[1];
    const float e2z = p2[2] - p0[2];
    float nx = e1y * e2z - e1z * e2y;
    float ny = e1z * e2x - e1x * e2z;
    float nz = e1x * e2y - e1y * e2x;
    const float length = std::sqrt(nx * nx + ny * ny + nz * nz);
    if (length > 1e-9f) {
        nx /= length; ny /= length; nz /= length;
    } else {
        // Degenerate (collinear) — keep a sensible default; renderer will see weak lighting.
        nx = 0.0f; ny = 0.0f; nz = 1.0f;
    }
    Face f{INVALID_ID, {nx, ny, nz}, triangles, loop, true};

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

void HalfEdgeMesh::remove_edge(std::uint32_t e_id) {
    if (!edge_is_live(e_id)) {
        throw std::out_of_range("HalfEdgeMesh::remove_edge: edge " + std::to_string(e_id) + " is not live");
    }
    const std::uint32_t he_a = e_id * 2;
    const std::uint32_t he_b = he_a + 1;
    if (halfedges_[he_a].face != INVALID_ID || halfedges_[he_b].face != INVALID_ID) {
        throw std::invalid_argument("HalfEdgeMesh::remove_edge: edge " + std::to_string(e_id) + " still bordered by a face");
    }
    const std::uint32_t v_min = halfedges_[he_a].origin;
    const std::uint32_t v_max = halfedges_[he_b].origin;
    edge_index_.erase(pack_pair(v_min, v_max));
    halfedges_[he_a].alive = false;
    halfedges_[he_b].alive = false;
    dirty_ = true;
}

void HalfEdgeMesh::remove_vertex(std::uint32_t v_id) {
    if (!vertex_is_live(v_id)) {
        throw std::out_of_range("HalfEdgeMesh::remove_vertex: vertex " + std::to_string(v_id) + " is not live");
    }
    // Scan live half-edges; reject if any has origin == v_id.
    for (const auto& he : halfedges_) {
        if (he.alive && he.origin == v_id) {
            throw std::invalid_argument("HalfEdgeMesh::remove_vertex: vertex " + std::to_string(v_id) + " still has incident edges");
        }
    }
    const auto& v = vertices_[v_id];
    position_index_.erase(pack_position(v.pos[0], v.pos[1], v.pos[2]));
    vertices_[v_id].alive = false;
    dirty_ = true;
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

void HalfEdgeMesh::restore_vertex(std::uint32_t v_id, float x, float y, float z) {
    if (v_id >= vertices_.size()) {
        throw std::out_of_range("HalfEdgeMesh::restore_vertex: v_id " + std::to_string(v_id) + " out of range");
    }
    if (vertices_[v_id].alive) {
        throw std::logic_error("HalfEdgeMesh::restore_vertex: slot " + std::to_string(v_id) + " is already live");
    }
    if (x == 0.0f) x = 0.0f;
    if (y == 0.0f) y = 0.0f;
    if (z == 0.0f) z = 0.0f;
    vertices_[v_id].pos[0] = x;
    vertices_[v_id].pos[1] = y;
    vertices_[v_id].pos[2] = z;
    vertices_[v_id].alive = true;
    position_index_[pack_position(x, y, z)] = v_id;
    dirty_ = true;
}

void HalfEdgeMesh::restore_edge(std::uint32_t e_id, std::uint32_t v1_id, std::uint32_t v2_id) {
    const std::uint32_t he_a = e_id * 2;
    const std::uint32_t he_b = he_a + 1;
    if (he_b >= halfedges_.size()) {
        throw std::out_of_range("HalfEdgeMesh::restore_edge: e_id " + std::to_string(e_id) + " out of range");
    }
    if (halfedges_[he_a].alive || halfedges_[he_b].alive) {
        throw std::logic_error("HalfEdgeMesh::restore_edge: slot " + std::to_string(e_id) + " is already live");
    }
    const std::uint32_t v_min = std::min(v1_id, v2_id);
    const std::uint32_t v_max = std::max(v1_id, v2_id);
    halfedges_[he_a].origin = v_min;
    halfedges_[he_a].face = INVALID_ID;
    halfedges_[he_a].next = INVALID_ID;
    halfedges_[he_a].alive = true;
    halfedges_[he_b].origin = v_max;
    halfedges_[he_b].face = INVALID_ID;
    halfedges_[he_b].next = INVALID_ID;
    halfedges_[he_b].alive = true;
    edge_index_[pack_pair(v_min, v_max)] = e_id;
    dirty_ = true;
}

void HalfEdgeMesh::restore_face(std::uint32_t f_id,
                                 const std::vector<std::uint32_t>& loop,
                                 const std::vector<std::int32_t>& triangles) {
    if (f_id >= faces_.size()) {
        throw std::out_of_range("HalfEdgeMesh::restore_face: f_id " + std::to_string(f_id) + " out of range");
    }
    if (faces_[f_id].alive) {
        throw std::logic_error("HalfEdgeMesh::restore_face: slot " + std::to_string(f_id) + " is already live");
    }
    // Same wiring as add_face_from_loop but writes into the existing slot.
    const std::size_t n = loop.size();
    std::vector<std::uint32_t> loop_halfedges(n, INVALID_ID);
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t v_from = loop[i];
        const std::uint32_t v_to = loop[(i + 1) % n];
        const std::uint32_t v_min = std::min(v_from, v_to);
        const std::uint32_t v_max = std::max(v_from, v_to);
        auto it = edge_index_.find(pack_pair(v_min, v_max));
        if (it == edge_index_.end() || !edge_is_live(it->second)) {
            throw std::invalid_argument("HalfEdgeMesh::restore_face: edge ("
                + std::to_string(v_from) + ", " + std::to_string(v_to) + ") is missing");
        }
        loop_halfedges[i] = (v_from < v_to) ? (it->second * 2) : (it->second * 2 + 1);
    }
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t he = loop_halfedges[i];
        halfedges_[he].next = loop_halfedges[(i + 1) % n];
        halfedges_[he].face = f_id;
    }
    Face& f = faces_[f_id];
    f.boundary_he = loop_halfedges[0];
    f.tris = triangles;
    f.loop = loop;
    f.alive = true;
    // Recompute geometric normal (same logic as add_face_from_loop) so that
    // undo→redo round-trips produce the correct normal rather than preserving
    // a stale value from before the fix.
    {
        const auto& rp0 = vertices_[loop[0]].pos;
        const auto& rp1 = vertices_[loop[1]].pos;
        const auto& rp2 = vertices_[loop[2]].pos;
        const float re1x = rp1[0] - rp0[0];
        const float re1y = rp1[1] - rp0[1];
        const float re1z = rp1[2] - rp0[2];
        const float re2x = rp2[0] - rp0[0];
        const float re2y = rp2[1] - rp0[1];
        const float re2z = rp2[2] - rp0[2];
        float rnx = re1y * re2z - re1z * re2y;
        float rny = re1z * re2x - re1x * re2z;
        float rnz = re1x * re2y - re1y * re2x;
        const float rlen = std::sqrt(rnx * rnx + rny * rny + rnz * rnz);
        if (rlen > 1e-9f) {
            rnx /= rlen; rny /= rlen; rnz /= rlen;
        } else {
            rnx = 0.0f; rny = 0.0f; rnz = 1.0f;
        }
        f.normal[0] = rnx; f.normal[1] = rny; f.normal[2] = rnz;
    }
    dirty_ = true;
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

namespace {

inline std::array<float, 3> sub3(std::array<float, 3> a, std::array<float, 3> b) {
    return { a[0]-b[0], a[1]-b[1], a[2]-b[2] };
}
inline std::array<float, 3> cross3(std::array<float, 3> a, std::array<float, 3> b) {
    return {
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    };
}
inline float dot3(std::array<float, 3> a, std::array<float, 3> b) {
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}
inline float len3(std::array<float, 3> a) {
    return std::sqrt(dot3(a, a));
}

// Compute geometric face normal from the first three boundary vertices.
// Returns zero vector if the face is degenerate (collinear or repeated vertices).
std::array<float, 3> compute_face_normal_geometric(
        const pluton::HalfEdgeMesh& m, std::uint32_t f_id) {
    auto loop = m.face_loop_vertices(f_id);
    if (loop.size() < 3) return {0, 0, 0};
    auto p0 = m.vertex_position(loop[0]);
    auto p1 = m.vertex_position(loop[1]);
    auto p2 = m.vertex_position(loop[2]);
    auto n  = cross3(sub3(p1, p0), sub3(p2, p0));
    float L = len3(n);
    if (L < 1e-7f) return {0, 0, 0};
    return { n[0]/L, n[1]/L, n[2]/L };
}

}  // namespace

bool pluton::HalfEdgeMesh::faces_are_coplanar(std::uint32_t f1_id,
                                              std::uint32_t f2_id,
                                              float angle_tol_cos,
                                              float dist_tol) const {
    if (!face_is_live(f1_id) || !face_is_live(f2_id)) return false;
    auto n1 = compute_face_normal_geometric(*this, f1_id);
    auto n2 = compute_face_normal_geometric(*this, f2_id);
    // Degenerate normal → refuse.
    if (len3(n1) < 1e-7f || len3(n2) < 1e-7f) return false;

    // Angle test: |dot(n1, n2)| > tolerance — accept either winding direction.
    float ang = std::abs(dot3(n1, n2));
    if (ang < angle_tol_cos) return false;

    // Distance test: every vertex of f2 within `dist_tol` of f1's plane, and vv.
    auto check_side = [&](std::array<float, 3> n, std::uint32_t plane_face,
                          std::uint32_t other_face) -> bool {
        auto plane_loop = face_loop_vertices(plane_face);
        auto p_anchor = vertex_position(plane_loop[0]);
        float d_anchor = dot3(n, p_anchor);
        for (auto v : face_loop_vertices(other_face)) {
            auto p = vertex_position(v);
            float signed_d = dot3(n, p) - d_anchor;
            if (std::abs(signed_d) > dist_tol) return false;
        }
        return true;
    };
    return check_side(n1, f1_id, f2_id) && check_side(n2, f2_id, f1_id);
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
