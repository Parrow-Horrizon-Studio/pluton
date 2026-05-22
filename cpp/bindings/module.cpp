#include <cstdint>

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include "pluton/halfedge.h"
#include "pluton/mesh.h"
#include "pluton/primitives.h"
#include "pluton/version.h"

namespace nb = nanobind;
using pluton::HalfEdgeMesh;
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

    nb::class_<HalfEdgeMesh>(m, "HalfEdgeMesh", "Half-edge topology mesh — geometric source of truth")
        .def(nb::init<>())

        // Mutators
        .def("add_vertex", &HalfEdgeMesh::add_vertex)
        .def("add_halfedge_pair", &HalfEdgeMesh::add_halfedge_pair)
        .def("add_face_from_loop", &HalfEdgeMesh::add_face_from_loop)
        .def("remove_vertex", &HalfEdgeMesh::remove_vertex)
        .def("remove_edge", &HalfEdgeMesh::remove_edge)
        .def("remove_face", &HalfEdgeMesh::remove_face)
        .def("restore_vertex", &HalfEdgeMesh::restore_vertex)
        .def("restore_edge", &HalfEdgeMesh::restore_edge)
        .def("restore_face", &HalfEdgeMesh::restore_face)
        .def("clear", &HalfEdgeMesh::clear)

        // Queries
        .def("vertex_is_live", &HalfEdgeMesh::vertex_is_live)
        .def("edge_is_live", &HalfEdgeMesh::edge_is_live)
        .def("face_is_live", &HalfEdgeMesh::face_is_live)
        .def("vertex_position", &HalfEdgeMesh::vertex_position)
        .def("edge_vertices", &HalfEdgeMesh::edge_vertices)
        .def("face_loop_vertices", &HalfEdgeMesh::face_loop_vertices)
        .def("face_triangles", &HalfEdgeMesh::face_triangles)

        // Half-edge adjacency (used by M3b push/pull)
        .def("halfedge_origin", &HalfEdgeMesh::halfedge_origin)
        .def("halfedge_next", &HalfEdgeMesh::halfedge_next)
        .def("halfedge_twin", &HalfEdgeMesh::halfedge_twin)
        .def("halfedge_face", &HalfEdgeMesh::halfedge_face)

        // Iteration
        .def("next_live_vertex", &HalfEdgeMesh::next_live_vertex, nb::arg("start") = 0u)
        .def("next_live_edge", &HalfEdgeMesh::next_live_edge, nb::arg("start") = 0u)
        .def("next_live_face", &HalfEdgeMesh::next_live_face, nb::arg("start") = 0u)

        // Buffer projection
        .def("edge_line_buffer", &HalfEdgeMesh::edge_line_buffer)
        .def("face_triangle_buffer", &HalfEdgeMesh::face_triangle_buffer)

        // Dirty flag
        .def("is_dirty", &HalfEdgeMesh::is_dirty)
        .def("mark_clean", &HalfEdgeMesh::mark_clean)

        // Slab introspection (mostly for tests)
        .def("vertex_slab_size", &HalfEdgeMesh::vertex_slab_size)
        .def("halfedge_slab_size", &HalfEdgeMesh::halfedge_slab_size)
        .def("face_slab_size", &HalfEdgeMesh::face_slab_size)

        .def_ro_static("INVALID_ID", &HalfEdgeMesh::INVALID_ID);
}
