#pragma once

#include "pluton/mesh.h"

namespace pluton {

/// Axis-aligned cube primitive.
///
/// Bottom face sits on z = 0 (the world ground plane); x and y span
/// [-size/2, +size/2]; z spans [0, size]. Each of the 6 faces has its own
/// outward-pointing normal (flat shading), so corner vertices are duplicated
/// per face — 24 vertices, 36 indices total.
///
/// @param size  Edge length of the cube. Defaults to 1.0.
Mesh make_cube(float size = 1.0f);

}  // namespace pluton
