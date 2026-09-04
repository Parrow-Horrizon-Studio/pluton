# Pluton

An open-source polygonal 3D modeler with CAD-like precision, aimed at architectural 3D modeling.

Pluton is a long-horizon project inspired by Blender's development model, intended as a free alternative to SketchUp Pro.

## Status

**Alpha, v0.5.0.** Phase 2 (Modeling App) is complete: you can draw, push/pull, transform,
organize, paint, annotate, save, and import/export real models. v0.4.0 gave it the surface of a
real application: seven dockable toolbars over an original icon set, per-tool cursors,
right-click context menus, and a layout that persists between runs. v0.5.0
([M7.3](docs/2026-05-16-pluton-design.md)) replaced the right-hand Materials, Tags and Scenes
docks and the three floating tool-option bars with a single Outliner and Properties panel: a
model hierarchy with per-instance visibility and rename, above five icon tabs (Tool Settings,
Entity Info, Material, Tags, Scenes). Still missing: the rest of
[Phase 2.5 (Parity & Polish)](docs/2026-05-16-pluton-design.md) (v0.4 to v0.8), and installers.
Run it from source.

## What works today

**Drawing** — Line, Rectangle, Circle, Polygon, Arc, and Push/Pull on the ground plane or on
any existing face, over a half-edge kernel that keeps topology clean.

**Inferencing & precision** — endpoint / midpoint / on-edge / on-face / intersection snaps,
3D axis-lock including the vertical axis, and a Measurements box (VCB) for typed exact values
on every tool. Metric and architectural imperial units, switchable per document.

**Editing** — Select (click, Shift-toggle, box-select), Eraser, Move, Rotate, Scale, and a
measure-only Tape Measure. Full undo/redo on everything.

**Organization** — Groups and Components with real instancing: enter-to-edit isolation with a
breadcrumb, shared-definition edit propagation, Make Unique, Explode, and Ctrl-drag copy.
Tags (layers) with per-tag visibility.

**Architecture tools** — a chaining Wall tool, Door/Window placement that auto-orients flush
to a wall face and shares one Component per identical opening, parametric Gable/Hip/Shed
Roofs, and persistent Dimension and Text annotations that live per editing context.

**Presentation** — solid-color materials with a Paint tool and per-material draw batching;
four face styles (Wireframe / Hidden Line / Monochrome / Shaded) plus an X-Ray toggle; and
Scenes — saved camera + tag visibility + style, recalled with an animated camera tween.

**File I/O** — a versioned native `.pluton` format (zip container, atomic writes, component
sharing preserved by identity), plus OBJ and glTF/GLB import and export. glTF goes through
Assimp and handles Draco-compressed meshes, reconstructing real instancing on import.

### Keyboard shortcuts

| Key | Tool | Key | Tool | Key | Tool |
|---|---|---|---|---|---|
| `Space` | Select | `M` | Move | `W` | Wall |
| `L` | Line | `Q` | Rotate | `D` | Door/Window |
| `R` | Rectangle | `S` | Scale | `O` | Roof |
| `C` | Circle | `E` | Eraser | `I` | Dimension |
| `G` | Polygon | `B` | Paint | `N` | Text |
| `A` | Arc | `T` | Tape Measure | `P` | Push/Pull |

`Ctrl+G` group · `Ctrl+Shift+G` component · `Ctrl+Shift+E` explode · `Ctrl+Z` / `Ctrl+Y`
undo/redo · `Esc` cancel · `Enter` finish gesture

## Architecture

- **Python 3.13** (PySide6 / Qt 6): UI shell, tools, scene graph, file I/O
- **C++20**: the half-edge geometry kernel and hot paths, exposed to Python via **nanobind**
- **moderngl / OpenGL**: viewport rendering
- **Assimp**: glTF/GLB decoding (statically linked; the only C++ format dependency)

CGAL is named in the design document for future volumetric booleans, but is **not** a
dependency today — the modeling operations shipped so far are pure half-edge work.

See [the design document](docs/2026-05-16-pluton-design.md) for the full architecture and
roadmap; each milestone has its own design and plan under [`docs/`](docs/).

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

The first build compiles Assimp from vcpkg and takes a while; later builds are incremental.
On Windows the `x64-windows-static-md` triplet is selected automatically, so the `_core`
extension bundles no runtime DLLs.

## Running

```bash
pluton
```

## Tests

Python suite:

```bash
pytest
```

C++ kernel suite — configure, build, and run with CTest:

```bash
cmake -S . -B build/tests -G Ninja && cmake --build build/tests && ctest --test-dir build/tests
```

On Windows, run that from a Developer Command Prompt (or after sourcing `vcvars64.bat`) —
without the MSVC environment the build silently does nothing.

Lint, at the versions CI pins:

```bash
ruff check python/pluton && ruff format --check python/pluton
```

CI runs the full build and both suites on windows-2022 and ubuntu-24.04, plus the lint gate,
on every push.

## License

GPL-3.0 or later. See [LICENSE](LICENSE).
