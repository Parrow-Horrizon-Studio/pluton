#include "pluton/primitives.h"

namespace pluton {

Mesh make_cube(float size) {
    const float h = size * 0.5f;

    Mesh mesh;
    mesh.positions.reserve(72);
    mesh.normals.reserve(72);
    mesh.indices.reserve(36);

    struct Face {
        float v[4][3];
        float n[3];
    };

    const Face faces[6] = {
        // +X face (right): normal (1, 0, 0)
        {{{+h, -h, 0.f}, {+h, +h, 0.f}, {+h, +h, size}, {+h, -h, size}}, {1.f, 0.f, 0.f}},
        // -X face (left): normal (-1, 0, 0)
        {{{-h, +h, 0.f}, {-h, -h, 0.f}, {-h, -h, size}, {-h, +h, size}}, {-1.f, 0.f, 0.f}},
        // +Y face (back): normal (0, 1, 0)
        {{{+h, +h, 0.f}, {-h, +h, 0.f}, {-h, +h, size}, {+h, +h, size}}, {0.f, 1.f, 0.f}},
        // -Y face (front): normal (0, -1, 0)
        {{{-h, -h, 0.f}, {+h, -h, 0.f}, {+h, -h, size}, {-h, -h, size}}, {0.f, -1.f, 0.f}},
        // +Z face (top): normal (0, 0, 1)
        {{{-h, -h, size}, {+h, -h, size}, {+h, +h, size}, {-h, +h, size}}, {0.f, 0.f, 1.f}},
        // -Z face (bottom): normal (0, 0, -1)
        {{{-h, +h, 0.f}, {+h, +h, 0.f}, {+h, -h, 0.f}, {-h, -h, 0.f}}, {0.f, 0.f, -1.f}},
    };

    for (const auto& face : faces) {
        const std::uint32_t base = static_cast<std::uint32_t>(mesh.vertex_count());
        for (int v = 0; v < 4; ++v) {
            mesh.positions.push_back(face.v[v][0]);
            mesh.positions.push_back(face.v[v][1]);
            mesh.positions.push_back(face.v[v][2]);
            mesh.normals.push_back(face.n[0]);
            mesh.normals.push_back(face.n[1]);
            mesh.normals.push_back(face.n[2]);
        }
        mesh.indices.push_back(base + 0);
        mesh.indices.push_back(base + 1);
        mesh.indices.push_back(base + 2);
        mesh.indices.push_back(base + 0);
        mesh.indices.push_back(base + 2);
        mesh.indices.push_back(base + 3);
    }

    return mesh;
}

}  // namespace pluton
