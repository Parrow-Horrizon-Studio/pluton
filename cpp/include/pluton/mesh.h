#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace pluton {

/// A polygonal mesh stored as three flat, GPU-ready arrays.
///
/// Layout matches what OpenGL VBOs want: tightly-packed floats for positions
/// and normals, and a 32-bit index buffer for triangles. This avoids any
/// reshape or copy when the data is pulled to Python via nanobind.
class Mesh {
public:
    /// Vertex positions in XYZ order: [x0,y0,z0, x1,y1,z1, ...].
    std::vector<float> positions;

    /// Vertex normals in XYZ order, parallel to `positions` (same length).
    std::vector<float> normals;

    /// Triangle indices into `positions` / `normals` (3 indices per triangle).
    std::vector<std::uint32_t> indices;

    /// Number of vertices (positions.size() / 3).
    std::size_t vertex_count() const { return positions.size() / 3; }

    /// Number of triangles (indices.size() / 3).
    std::size_t triangle_count() const { return indices.size() / 3; }
};

}  // namespace pluton
