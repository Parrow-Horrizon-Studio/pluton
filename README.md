# Pluton

An open-source polygonal 3D modeler with CAD-like precision, aimed at architectural 3D modeling.

Pluton is a long-horizon project inspired by Blender's development model, intended as a free alternative to SketchUp Pro.

## Status

Pre-alpha — Milestone 0 (Foundation). The project is in early scaffolding. Nothing usable yet.

## Architecture

- **Python** (PySide6 / Qt 6): UI shell, tools, scene graph, file I/O, plugin system
- **C++20**: geometry kernel, hot paths (exposed to Python via nanobind)
- **CGAL**: computational geometry library (added at M3)

## Building from source

Requires Python 3.13+, CMake 3.27+, Ninja, a C++20 compiler, and vcpkg with `VCPKG_ROOT` set.

Set the CMake toolchain file env var (one-time per shell session):

**Linux/macOS:**
```bash
export CMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
```

**Windows (PowerShell):**
```powershell
$env:CMAKE_TOOLCHAIN_FILE = "$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake"
```

Then install in editable mode:

```bash
pip install -e ".[dev]"
```

## License

GPL-3.0 or later. See [LICENSE](LICENSE).
