#include "pluton/gltf_import.h"

#include <stdexcept>
#include <utility>

#include <assimp/Importer.hpp>
#include <assimp/material.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

namespace pluton {

namespace {

std::array<float, 16> to_row_major(const aiMatrix4x4& m) {
    return {m.a1, m.a2, m.a3, m.a4, m.b1, m.b2, m.b3, m.b4,
            m.c1, m.c2, m.c3, m.c4, m.d1, m.d2, m.d3, m.d4};
}

void collect_nodes(const aiNode* node, int parent, std::vector<ImportedNode>& out) {
    ImportedNode n;
    n.name = node->mName.C_Str();
    n.parent = parent;
    n.transform = to_row_major(node->mTransformation);
    n.mesh_indices.assign(node->mMeshes, node->mMeshes + node->mNumMeshes);
    const int my_index = static_cast<int>(out.size());
    out.push_back(std::move(n));
    for (unsigned i = 0; i < node->mNumChildren; ++i)
        collect_nodes(node->mChildren[i], my_index, out);
}

}  // namespace

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

    for (unsigned i = 0; i < scene->mNumMaterials; ++i) {
        const aiMaterial* mat = scene->mMaterials[i];
        ImportedMaterial im;
        aiString name;
        if (mat->Get(AI_MATKEY_NAME, name) == AI_SUCCESS) im.name = name.C_Str();
        aiColor4D color(0.8f, 0.8f, 0.8f, 1.0f);
        if (mat->Get(AI_MATKEY_BASE_COLOR, color) != AI_SUCCESS)
            mat->Get(AI_MATKEY_COLOR_DIFFUSE, color);
        im.base_color = {color.r, color.g, color.b, color.a};
        result.materials.push_back(std::move(im));
    }

    for (unsigned i = 0; i < scene->mNumMeshes; ++i) {
        const aiMesh* mesh = scene->mMeshes[i];
        ImportedMesh om;
        om.material_index = static_cast<int>(mesh->mMaterialIndex);
        om.positions.reserve(mesh->mNumVertices);
        for (unsigned v = 0; v < mesh->mNumVertices; ++v) {
            const aiVector3D& p = mesh->mVertices[v];
            om.positions.push_back({p.x, p.y, p.z});
        }
        om.triangles.reserve(mesh->mNumFaces);
        for (unsigned f = 0; f < mesh->mNumFaces; ++f) {
            const aiFace& face = mesh->mFaces[f];
            if (face.mNumIndices != 3) continue;
            om.triangles.push_back(
                {face.mIndices[0], face.mIndices[1], face.mIndices[2]});
        }
        result.meshes.push_back(std::move(om));
    }

    collect_nodes(scene->mRootNode, -1, result.nodes);
    return result;
}

}  // namespace pluton
