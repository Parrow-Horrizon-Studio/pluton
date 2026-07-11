#include "pluton/gltf_import.h"

#include <stdexcept>
#include <utility>

#include <assimp/Importer.hpp>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

namespace pluton {

// Task 0 build spike: genuinely call Assimp (proving the link + Draco decode)
// but only return mesh 0's positions. The full aiScene walk (all meshes,
// triangles, materials, nodes) lands in Task 1.
ImportedScene import_gltf(const std::string& path) {
    Assimp::Importer importer;
    const aiScene* scene = importer.ReadFile(
        path, aiProcess_Triangulate | aiProcess_JoinIdenticalVertices);
    if (scene == nullptr || (scene->mFlags & AI_SCENE_FLAGS_INCOMPLETE) != 0
        || scene->mRootNode == nullptr) {
        throw std::runtime_error(std::string("glTF import failed: ")
                                 + importer.GetErrorString());
    }

    ImportedScene result;
    if (scene->mNumMeshes > 0) {
        const aiMesh* mesh = scene->mMeshes[0];
        ImportedMesh om;
        om.material_index = -1;
        om.positions.reserve(mesh->mNumVertices);
        for (unsigned v = 0; v < mesh->mNumVertices; ++v) {
            const aiVector3D& p = mesh->mVertices[v];
            om.positions.push_back({p.x, p.y, p.z});
        }
        result.meshes.push_back(std::move(om));
    }
    return result;
}

}  // namespace pluton
