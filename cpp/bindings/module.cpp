#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include "pluton/version.h"

namespace nb = nanobind;

NB_MODULE(_core, m) {
    m.doc() = "Pluton C++ core module";

    m.def("version", &pluton::version,
          "Returns the Pluton library version as a string.");
}
