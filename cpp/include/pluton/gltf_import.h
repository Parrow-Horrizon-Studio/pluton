#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace pluton {

struct ImportedMaterial {
    std::string name;
    std::array<float, 4> base_color;  // RGBA
};

struct ImportedMesh {
    std::vector<std::array<float, 3>> positions;
    std::vector<std::array<std::uint32_t, 3>> triangles;
    int material_index;  // -1 = none
};

struct ImportedNode {
    std::string name;
    int parent;                       // -1 = root
    std::array<float, 16> transform;  // row-major (aiMatrix4x4 order)
    std::vector<int> mesh_indices;
};

struct ImportedScene {
    std::vector<ImportedNode> nodes;
    std::vector<ImportedMesh> meshes;
    std::vector<ImportedMaterial> materials;
};

// Load a glTF/GLB and flatten to neutral data. Throws std::runtime_error on a
// whole-file load failure (missing/undecodable).
ImportedScene import_gltf(const std::string& path);

}  // namespace pluton
