#include <gtest/gtest.h>

#include <cstdlib>
#include <string>

#include "pluton/gltf_import.h"

namespace {

std::string sample(const char* name) {
    // Tests run from the build dir; PLUTON_TEST_DATA is set by CMake.
    return std::string(PLUTON_TEST_DATA) + "/gltf/" + name;
}

TEST(GltfImport, PlainBoxHasGeometryAndNodes) {
    const pluton::ImportedScene s = pluton::import_gltf(sample("plain_box.glb"));
    ASSERT_FALSE(s.meshes.empty());
    EXPECT_GT(s.meshes[0].positions.size(), 0u);
    EXPECT_GT(s.meshes[0].triangles.size(), 0u);
    EXPECT_FALSE(s.nodes.empty());
    EXPECT_EQ(s.nodes[0].parent, -1);           // root first
}

TEST(GltfImport, DracoBoxDecodes) {
    const pluton::ImportedScene s = pluton::import_gltf(sample("draco_box.glb"));
    ASSERT_FALSE(s.meshes.empty());
    EXPECT_GT(s.meshes[0].triangles.size(), 0u);  // Draco actually decoded
}

TEST(GltfImport, MissingFileThrows) {
    EXPECT_THROW(pluton::import_gltf(sample("does_not_exist.glb")), std::runtime_error);
}

}  // namespace
