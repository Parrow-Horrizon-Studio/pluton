#include <cstdint>

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

#include "pluton/mesh.h"
#include "pluton/primitives.h"
#include "pluton/version.h"

namespace nb = nanobind;
using pluton::Mesh;

namespace {

// Expose std::vector<float> as a read-only (N, 3) numpy view of the data.
// The `const float` dtype is what makes the resulting numpy array
// non-writable from Python. The `nb::rv_policy::reference_internal` policy
// on the def_prop_ro call (below) keeps the owning Mesh alive as long as
// the returned ndarray is alive.
nb::ndarray<const float, nb::numpy, nb::shape<-1, 3>> as_vec3_array(
    const std::vector<float>& v) {
    const std::size_t n = v.size() / 3;
    return nb::ndarray<const float, nb::numpy, nb::shape<-1, 3>>(
        const_cast<float*>(v.data()),
        {n, static_cast<std::size_t>(3)});
}

nb::ndarray<const std::uint32_t, nb::numpy, nb::shape<-1>> as_index_array(
    const std::vector<std::uint32_t>& v) {
    return nb::ndarray<const std::uint32_t, nb::numpy, nb::shape<-1>>(
        const_cast<std::uint32_t*>(v.data()),
        {v.size()});
}

}  // namespace

NB_MODULE(_core, m) {
    m.doc() = "Pluton C++ core module";

    m.def("version", &pluton::version,
          "Returns the Pluton library version as a string.");

    nb::class_<Mesh>(m, "Mesh", "Polygonal mesh: positions, normals, indices.")
        .def(nb::init<>())
        .def_prop_ro(
            "positions",
            [](Mesh& self) { return as_vec3_array(self.positions); },
            nb::rv_policy::reference_internal,
            "Vertex positions as a read-only (N, 3) float32 numpy view.")
        .def_prop_ro(
            "normals",
            [](Mesh& self) { return as_vec3_array(self.normals); },
            nb::rv_policy::reference_internal,
            "Vertex normals as a read-only (N, 3) float32 numpy view.")
        .def_prop_ro(
            "indices",
            [](Mesh& self) { return as_index_array(self.indices); },
            nb::rv_policy::reference_internal,
            "Triangle indices as a read-only (M,) uint32 numpy view.")
        .def_prop_ro("vertex_count", &Mesh::vertex_count)
        .def_prop_ro("triangle_count", &Mesh::triangle_count);

    m.def("make_cube", &pluton::make_cube, nb::arg("size") = 1.0f,
          "Create an axis-aligned cube of the given edge length, "
          "with its bottom face on the ground plane (z = 0).");
}
