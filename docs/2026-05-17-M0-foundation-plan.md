# M0 — Foundation: Hello, Window — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get a Qt window open with a triangle drawn via QOpenGLWidget, with the Python ↔ C++ binding pipeline (via nanobind) working end-to-end, building cleanly through scikit-build-core + CMake + vcpkg, tested by pytest + GoogleTest, and verified green by GitHub Actions on Windows and Linux.

**Architecture:** Hybrid Python + C++. scikit-build-core orchestrates `pip install` to drive CMake, which builds a C++ shared library exposed to Python through nanobind. PySide6 (Qt 6) provides the window and the OpenGL surface (QOpenGLWidget). Direct OpenGL calls draw the triangle (ModernGL comes later in M1; M0 keeps the viewport minimal). vcpkg manages C++ dependencies via manifest mode. Tests run via pytest (Python) and GoogleTest (C++). CI runs on Windows + Linux via GitHub Actions.

**Tech Stack:** Python 3.13+, C++20 (MSVC on Windows, GCC on Linux), CMake 3.27+, Ninja, vcpkg (manifest mode), scikit-build-core, nanobind 2.x, PySide6 6.7+, pytest, GoogleTest, Ruff, clang-format, GitHub Actions.

---

## Prerequisites (one-time, manual)

Before starting, ensure your development environment has:

1. **Python 3.13+** installed and on PATH
2. **Visual Studio 2022** with "Desktop development with C++" workload (Windows) OR **GCC 12+** (Linux)
3. **CMake 3.27+** on PATH
4. **Ninja** on PATH
5. **Git** on PATH
6. **vcpkg** cloned somewhere stable (e.g., `C:\dev\vcpkg` on Windows or `~/dev/vcpkg` on Linux):
   ```bash
   git clone https://github.com/microsoft/vcpkg.git
   cd vcpkg
   ./bootstrap-vcpkg.sh    # or .bat on Windows
   ```
7. **`VCPKG_ROOT` environment variable** set to the vcpkg directory
8. **Qt installer**: install Qt 6.7+ via the Qt online installer (vcpkg's Qt build is fragile). PySide6 will use its bundled Qt for the Python side; this Qt install is for any C++ Qt code we add later. For M0, **the Qt installer is optional** — PySide6 alone is sufficient.

If any of these are missing, install them first.

---

## File Structure (target at end of M0)

```
pluton/
├── .github/
│   └── workflows/
│       └── build.yml             # CI for Windows + Linux
├── .gitignore
├── LICENSE                       # GPL-3.0
├── README.md
├── CMakeLists.txt                # Top-level CMake (delegates to cpp/)
├── vcpkg.json                    # C++ dependency manifest
├── pyproject.toml                # Python + scikit-build-core config
├── .clang-format                 # C++ formatting rules
├── cpp/
│   ├── CMakeLists.txt            # C++ build configuration
│   ├── include/
│   │   └── pluton/
│   │       └── version.h         # Public header: pluton::version()
│   ├── src/
│   │   └── version.cpp           # Implementation of version()
│   ├── bindings/
│   │   └── module.cpp            # nanobind module definition
│   └── tests/
│       ├── CMakeLists.txt
│       └── test_version.cpp      # GoogleTest tests for version()
├── python/
│   └── pluton/
│       ├── __init__.py           # Re-exports from _core
│       ├── __main__.py           # `python -m pluton` entry point
│       ├── app.py                # Main application bootstrap
│       ├── ui/
│       │   ├── __init__.py
│       │   └── main_window.py    # QMainWindow subclass
│       └── viewport/
│           ├── __init__.py
│           └── viewport_widget.py # QOpenGLWidget subclass with triangle
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # pytest configuration
│   ├── test_binding.py           # Tests for the nanobind module
│   └── test_window.py            # Smoke test that the window can be constructed
└── docs/
    ├── 2026-05-16-pluton-design.md
    └── 2026-05-17-M0-foundation-plan.md   (this file)
```

**File responsibilities:**

- `cpp/include/pluton/` — public C++ headers (anything the Python binding layer or external consumers might call)
- `cpp/src/` — C++ implementation
- `cpp/bindings/` — nanobind glue code (this is the *only* place the C++ library cares about Python)
- `python/pluton/` — the Python application; imports the compiled C++ module as `pluton._core`
- `python/pluton/ui/` — Qt widget code (UI shell)
- `python/pluton/viewport/` — the 3D viewport widget
- `tests/` — Python-level integration tests (uses pytest)
- `cpp/tests/` — C++ unit tests (uses GoogleTest)
- `.github/workflows/build.yml` — CI workflow for Windows + Linux

---

## Tasks

> Each task is self-contained and ends with a commit. Tasks are designed to be executed in order — later tasks build on earlier ones. Each step takes 2–5 minutes.
>
> **After every commit step below, also run `git push`** to keep the remote up to date. The remote is set up in Task 1 (create the GitHub repo + push the initial commit). Pushing after every task means: backup of work, visible CI runs (once CI exists in Task 15), and no risk of losing local work to machine issues.

---

### Task 1: Initialize repository — local + GitHub remote

**Files:**
- Create: `pluton/LICENSE`
- Create: `pluton/README.md`
- Create: `pluton/.gitignore`
- Remote setup: create `Parrow-Horrizon-Studio/pluton` on GitHub

- [ ] **Step 1: Create LICENSE file (GPL-3.0)**

Download the full GPL-3.0 license text from https://www.gnu.org/licenses/gpl-3.0.txt and save it to `pluton/LICENSE`. The full text is too long to include inline here, but it's the standard GPL-3.0 license — get the exact text from the GNU site.

- [ ] **Step 2: Create README.md**

Write to `pluton/README.md`:

````markdown
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

```bash
pip install -e .
```

## License

GPL-3.0 or later. See [LICENSE](LICENSE).
````

- [ ] **Step 3: Create .gitignore**

Write to `pluton/.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
*.egg
.pytest_cache/
.ruff_cache/
.mypy_cache/
build/
dist/
.venv/
venv/

# C++
*.o
*.obj
*.so
*.dylib
*.pyd
*.dll
*.a
*.lib
*.exp
*.ilk
*.pdb

# CMake
CMakeFiles/
CMakeCache.txt
cmake_install.cmake
Makefile
*.cmake
!CMakeLists.txt
!*.cmake.in
_deps/

# scikit-build
_skbuild/

# vcpkg
vcpkg_installed/

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db
```

- [ ] **Step 4: Initialize git repository and create first commit**

Run from `pluton/`:
```bash
git init
git branch -M main
git add LICENSE README.md .gitignore
git commit -m "chore: initial commit — LICENSE, README, .gitignore"
```

Expected: Repository initialized on `main` branch; first commit created.

- [ ] **Step 5: Create the GitHub repository under the org**

**Option A — via the GitHub web UI (simpler if you've never used `gh` CLI):**

1. Open https://github.com/organizations/Parrow-Horrizon-Studio/repositories/new in your browser
2. Repository name: `pluton`
3. Description: `Polygonal 3D modeler for architecture — free alternative to SketchUp Pro`
4. Visibility: **Public**
5. **Do NOT** check "Add a README", "Add .gitignore", or "Choose a license" — we already have those locally. Creating with any of these would create commits on GitHub that we'd have to merge with ours, complicating the first push.
6. Click **"Create repository"**

**Option B — via `gh` CLI (faster if you have GitHub CLI installed and authenticated):**

```bash
gh repo create Parrow-Horrizon-Studio/pluton \
    --public \
    --description "Polygonal 3D modeler for architecture — free alternative to SketchUp Pro"
```

Either way, the result is an empty `Parrow-Horrizon-Studio/pluton` repository on GitHub, ready to receive our initial push.

- [ ] **Step 6: Add the remote and push the initial commit**

Run from `pluton/`:

```bash
git remote add origin git@github.com:Parrow-Horrizon-Studio/pluton.git
git push -u origin main
```

Expected: `main` branch pushed to GitHub; the `-u` flag sets up upstream tracking so future `git push` commands don't need extra arguments.

**Note on SSH vs HTTPS:** the URL above assumes you've already set up SSH keys on GitHub (we did this during the org calibration session). If you prefer HTTPS, use `https://github.com/Parrow-Horrizon-Studio/pluton.git` instead. SSH is recommended.

After this step, visit `https://github.com/Parrow-Horrizon-Studio/pluton` and confirm the LICENSE, README, and .gitignore are visible. The Verified badge should appear on the commit (signed via your SSH signing key, which we also set up earlier).

---

### Task 2: Create top-level CMakeLists.txt

**Files:**
- Create: `pluton/CMakeLists.txt`

- [ ] **Step 1: Write top-level CMakeLists.txt**

Write to `pluton/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.27)

# Project metadata
project(pluton
    VERSION 0.0.1
    DESCRIPTION "Polygonal 3D modeler for architecture"
    LANGUAGES CXX
)

# Require C++20 globally
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Generate compile_commands.json for IDE support (clangd, etc.)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Compiler warning baseline
if(MSVC)
    add_compile_options(/W4)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find Python (driven by scikit-build-core at build time)
find_package(Python 3.13 COMPONENTS Interpreter Development.Module REQUIRED)

# Find nanobind (installed via pip as a build dep — scikit-build-core handles this)
find_package(nanobind CONFIG REQUIRED)

# Add C++ source tree
add_subdirectory(cpp)

# Enable tests if this is the top-level project (not when consumed as a subproject)
if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    enable_testing()
    add_subdirectory(cpp/tests)
endif()
```

- [ ] **Step 2: Commit**

```bash
git add CMakeLists.txt
git commit -m "build: add top-level CMakeLists.txt with C++20 baseline"
```

---

### Task 3: Create vcpkg.json manifest

**Files:**
- Create: `pluton/vcpkg.json`

- [ ] **Step 1: Write vcpkg manifest**

Write to `pluton/vcpkg.json`:

```json
{
    "name": "pluton",
    "version": "0.0.1",
    "description": "Polygonal 3D modeler for architecture",
    "homepage": "https://pluton3d.org",
    "license": "GPL-3.0-or-later",
    "dependencies": [
        "gtest"
    ]
}
```

Note: nanobind is NOT in vcpkg.json — it's installed via pip as a build-system requirement (handled in the next task via `pyproject.toml`). vcpkg handles pure-C++ deps; pip-installable bindings tools come through Python's package system.

Note on dependency form: we use the **bare string form** (`"gtest"`) rather than the object form with `version>=`. The object form with version constraints requires a `builtin-baseline` field that pins a specific vcpkg registry commit, which adds reproducibility but also setup overhead we don't need at this stage. The bare-string form tells vcpkg to install whatever current version is in its registry — appropriate for a learning/early-stage project. We can add `builtin-baseline` later when version-pinning becomes important for CI reproducibility.

- [ ] **Step 2: Commit**

```bash
git add vcpkg.json
git commit -m "build: add vcpkg manifest with GoogleTest dependency"
```

---

### Task 4: Create pyproject.toml with scikit-build-core configuration

**Files:**
- Create: `pluton/pyproject.toml`

- [ ] **Step 1: Write pyproject.toml**

Write to `pluton/pyproject.toml`:

```toml
[build-system]
requires = [
    "scikit-build-core>=0.10",
    "nanobind>=2.0"
]
build-backend = "scikit_build_core.build"

[project]
name = "pluton"
version = "0.0.1"
description = "Polygonal 3D modeler for architecture"
readme = "README.md"
license = { file = "LICENSE" }
authors = [
    { name = "Rowee Apor", email = "roweeapor@gmail.com" }
]
requires-python = ">=3.13"
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    "Programming Language :: Python :: 3.13",
    "Topic :: Multimedia :: Graphics :: 3D Modeling",
    "Operating System :: Microsoft :: Windows",
    "Operating System :: POSIX :: Linux"
]
dependencies = [
    "PySide6>=6.7"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.4",
    "ruff>=0.5",
    "mypy>=1.10"
]

[project.scripts]
pluton = "pluton.app:main"

# scikit-build-core configuration
[tool.scikit-build]
minimum-version = "0.10"
cmake.version = ">=3.27"
ninja.version = ">=1.11"
build-dir = "build/{wheel_tag}"
wheel.packages = ["python/pluton"]

# Ruff configuration
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "RUF"]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# pytest configuration
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-ra --strict-markers"
```

**Note on the vcpkg toolchain:** scikit-build-core doesn't directly support setting `CMAKE_TOOLCHAIN_FILE` from `pyproject.toml`. Instead, the developer sets it as an environment variable in their shell before running `pip install`. This is documented in the README (next step) and is a one-time-per-session setup.

- [ ] **Step 2: Update README.md with corrected build instructions**

Replace the "Building from source" section of `README.md` with:

````markdown
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
````

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml README.md
git commit -m "build: add pyproject.toml with scikit-build-core configuration"
```

---

### Task 5: Create C++ source tree with a `version()` function

**Files:**
- Create: `pluton/cpp/CMakeLists.txt`
- Create: `pluton/cpp/include/pluton/version.h`
- Create: `pluton/cpp/src/version.cpp`

- [ ] **Step 1: Create `cpp/include/pluton/version.h`**

Write to `pluton/cpp/include/pluton/version.h`:

```cpp
#pragma once

#include <string>

namespace pluton {

/// Returns the Pluton library version as a string (e.g., "0.0.1").
std::string version();

}  // namespace pluton
```

- [ ] **Step 2: Create `cpp/src/version.cpp`**

Write to `pluton/cpp/src/version.cpp`:

```cpp
#include "pluton/version.h"

namespace pluton {

std::string version() {
    return "0.0.1";
}

}  // namespace pluton
```

- [ ] **Step 3: Create `cpp/CMakeLists.txt`**

Write to `pluton/cpp/CMakeLists.txt`:

```cmake
# Core library — the C++ implementation
add_library(pluton_core STATIC
    src/version.cpp
)

target_include_directories(pluton_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Position-independent code required when linking into a Python module
set_target_properties(pluton_core PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

# The nanobind module — exposed to Python as `pluton._core`
nanobind_add_module(_core
    bindings/module.cpp
)

target_link_libraries(_core PRIVATE pluton_core)

# Install the compiled module into the Python package directory
install(TARGETS _core LIBRARY DESTINATION pluton)
```

- [ ] **Step 4: Commit**

```bash
git add cpp/CMakeLists.txt cpp/include/pluton/version.h cpp/src/version.cpp
git commit -m "feat(cpp): add version() function and CMake target pluton_core"
```

---

### Task 6: Create the nanobind binding module

**Files:**
- Create: `pluton/cpp/bindings/module.cpp`

- [ ] **Step 1: Write the nanobind module**

Write to `pluton/cpp/bindings/module.cpp`:

```cpp
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include "pluton/version.h"

namespace nb = nanobind;

NB_MODULE(_core, m) {
    m.doc() = "Pluton C++ core module";

    m.def("version", &pluton::version,
          "Returns the Pluton library version as a string.");
}
```

This module exposes `pluton._core.version()` to Python. The `NB_MODULE(_core, m)` macro declares the module name (`_core`), which is how Python imports it (`from pluton import _core`).

- [ ] **Step 2: Commit**

```bash
git add cpp/bindings/module.cpp
git commit -m "feat(bindings): add nanobind module exposing version()"
```

---

### Task 7: Create the Python package structure

**Files:**
- Create: `pluton/python/pluton/__init__.py`
- Create: `pluton/python/pluton/__main__.py`
- Create: `pluton/python/pluton/app.py`

- [ ] **Step 1: Create `python/pluton/__init__.py`**

Write to `pluton/python/pluton/__init__.py`:

```python
"""Pluton — polygonal 3D modeler for architecture."""

from pluton._core import version

__version__ = version()

__all__ = ["version", "__version__"]
```

- [ ] **Step 2: Create `python/pluton/app.py` (minimal entry point)**

Write to `pluton/python/pluton/app.py`:

```python
"""Pluton application entry point."""

import sys


def main() -> int:
    """Application entry point. Returns process exit code."""
    from pluton import __version__
    print(f"Pluton {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

For now, `main()` just prints the version. We'll replace this with the Qt application bootstrap in Task 11.

- [ ] **Step 3: Create `python/pluton/__main__.py`**

Write to `pluton/python/pluton/__main__.py`:

```python
"""Allows `python -m pluton` to launch the application."""

import sys
from pluton.app import main


sys.exit(main())
```

- [ ] **Step 4: Commit**

```bash
git add python/pluton/__init__.py python/pluton/__main__.py python/pluton/app.py
git commit -m "feat(python): add minimal pluton package with version entry point"
```

---

### Task 8: First end-to-end build and verification

**Files:** None new — this task verifies the build.

- [ ] **Step 1: Ensure `CMAKE_TOOLCHAIN_FILE` is set**

In your shell:

**Linux/macOS:**
```bash
export CMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
```

**Windows (PowerShell):**
```powershell
$env:CMAKE_TOOLCHAIN_FILE = "$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake"
```

- [ ] **Step 2: Create a virtual environment and install in editable mode**

From `pluton/`:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -e ".[dev]"
```

Expected: scikit-build-core invokes CMake, CMake configures the project (downloads nanobind via pip, finds Python, finds vcpkg toolchain), compiles `pluton_core` and the `_core` module, installs them into the wheel layout, and pip installs the wheel in editable mode.

If anything fails, **stop and debug before continuing**. Common issues:
- `VCPKG_ROOT` not set → re-export and retry
- `CMAKE_TOOLCHAIN_FILE` not set → re-export and retry
- Compiler not found → install Visual Studio Build Tools (Windows) or build-essential (Linux)
- nanobind not found by CMake → make sure pip installed it (`pip list | grep nanobind`)

- [ ] **Step 3: Run the application**

```bash
python -m pluton
```

Expected output:
```
Pluton 0.0.1
```

This confirms that the C++ module compiled, was correctly installed into the Python package, and that `pluton.version()` (delegating to `pluton._core.version()`) returns the expected string. **End-to-end Python + C++ pipeline verified.**

- [ ] **Step 4: Commit (nothing changed — but tag a clean build state)**

```bash
git tag m0-first-build
```

This creates a local tag at the current commit so you can return to it.

---

### Task 9: Add pytest infrastructure and first Python test

**Files:**
- Create: `pluton/tests/__init__.py`
- Create: `pluton/tests/conftest.py`
- Create: `pluton/tests/test_binding.py`

- [ ] **Step 1: Create empty `tests/__init__.py`**

Write to `pluton/tests/__init__.py`:

```python
```

(An empty file — makes `tests/` a package.)

- [ ] **Step 2: Create `tests/conftest.py`**

Write to `pluton/tests/conftest.py`:

```python
"""Shared pytest fixtures and configuration."""

import pytest
```

(Minimal for now; we'll add fixtures as needed.)

- [ ] **Step 3: Write failing test for the nanobind module**

Write to `pluton/tests/test_binding.py`:

```python
"""Tests that verify the Python ↔ C++ binding pipeline."""

import re

from pluton import _core, version, __version__


def test_core_version_returns_string():
    result = _core.version()
    assert isinstance(result, str)


def test_core_version_matches_semver_pattern():
    result = _core.version()
    assert re.match(r"^\d+\.\d+\.\d+$", result), \
        f"Expected MAJOR.MINOR.PATCH format, got: {result!r}"


def test_top_level_version_function_delegates_to_core():
    assert version() == _core.version()


def test_dunder_version_matches_core():
    assert __version__ == _core.version()
```

- [ ] **Step 4: Run tests to verify they pass**

From `pluton/` (with `.venv` activated):

```bash
pytest tests/test_binding.py -v
```

Expected output:
```
tests/test_binding.py::test_core_version_returns_string PASSED
tests/test_binding.py::test_core_version_matches_semver_pattern PASSED
tests/test_binding.py::test_top_level_version_function_delegates_to_core PASSED
tests/test_binding.py::test_dunder_version_matches_core PASSED

4 passed
```

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py tests/test_binding.py
git commit -m "test: add pytest infrastructure and binding pipeline tests"
```

---

### Task 10: Add GoogleTest C++ tests

**Files:**
- Create: `pluton/cpp/tests/CMakeLists.txt`
- Create: `pluton/cpp/tests/test_version.cpp`

- [ ] **Step 1: Create `cpp/tests/test_version.cpp`**

Write to `pluton/cpp/tests/test_version.cpp`:

```cpp
#include <gtest/gtest.h>
#include <regex>

#include "pluton/version.h"

TEST(VersionTest, ReturnsNonEmptyString) {
    EXPECT_FALSE(pluton::version().empty());
}

TEST(VersionTest, MatchesSemverPattern) {
    const std::string v = pluton::version();
    const std::regex semver_pattern{R"(^\d+\.\d+\.\d+$)"};
    EXPECT_TRUE(std::regex_match(v, semver_pattern))
        << "Expected MAJOR.MINOR.PATCH, got: " << v;
}
```

- [ ] **Step 2: Create `cpp/tests/CMakeLists.txt`**

Write to `pluton/cpp/tests/CMakeLists.txt`:

```cmake
find_package(GTest CONFIG REQUIRED)

add_executable(pluton_tests
    test_version.cpp
)

target_link_libraries(pluton_tests PRIVATE
    pluton_core
    GTest::gtest
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(pluton_tests)
```

- [ ] **Step 3: Reconfigure the build to pick up the test target**

The C++ test target is built via CMake directly (not through `pip install`). From `pluton/`:

```bash
cmake -B build/tests -S . -G Ninja -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
cmake --build build/tests
```

(Windows: replace the `$VCPKG_ROOT` substitution with `$env:VCPKG_ROOT` in PowerShell.)

Expected: CMake configures, vcpkg installs GoogleTest if needed (first time only — takes a few minutes), and the `pluton_tests` executable builds.

- [ ] **Step 4: Run the C++ tests**

```bash
cd build/tests
ctest --output-on-failure
```

Expected output:
```
    Start 1: VersionTest.ReturnsNonEmptyString
1/2 Test #1: VersionTest.ReturnsNonEmptyString ...........   Passed    0.01 sec
    Start 2: VersionTest.MatchesSemverPattern
2/2 Test #2: VersionTest.MatchesSemverPattern ............   Passed    0.01 sec

100% tests passed
```

- [ ] **Step 5: Commit**

```bash
cd ../..  # back to pluton/
git add cpp/tests/CMakeLists.txt cpp/tests/test_version.cpp
git commit -m "test(cpp): add GoogleTest infrastructure with version tests"
```

---

### Task 11: Add PySide6 main window

**Files:**
- Create: `pluton/python/pluton/ui/__init__.py`
- Create: `pluton/python/pluton/ui/main_window.py`
- Modify: `pluton/python/pluton/app.py`

- [ ] **Step 1: Create `python/pluton/ui/__init__.py`**

Write to `pluton/python/pluton/ui/__init__.py`:

```python
"""Pluton UI components (PySide6 / Qt 6)."""
```

- [ ] **Step 2: Create `python/pluton/ui/main_window.py`**

Write to `pluton/python/pluton/ui/main_window.py`:

```python
"""The main application window."""

from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)
```

- [ ] **Step 3: Update `python/pluton/app.py` to launch the Qt application**

Replace the contents of `python/pluton/app.py` with:

```python
"""Pluton application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from pluton import __version__
from pluton.ui.main_window import MainWindow


def main() -> int:
    """Application entry point. Returns process exit code."""
    print(f"Pluton {__version__}")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify the window opens**

From `pluton/` (with `.venv` activated):

```bash
python -m pluton
```

Expected: A 1280x800 window titled "Pluton" opens. Close it to exit.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/__init__.py python/pluton/ui/main_window.py python/pluton/app.py
git commit -m "feat(ui): add PySide6 main window"
```

---

### Task 12: Add QOpenGLWidget viewport that draws a triangle

**Files:**
- Modify: `pluton/pyproject.toml` (add PyOpenGL dependency)
- Create: `pluton/python/pluton/viewport/__init__.py`
- Create: `pluton/python/pluton/viewport/viewport_widget.py`
- Modify: `pluton/python/pluton/ui/main_window.py`

- [ ] **Step 1: Add PyOpenGL dependency**

Edit `pluton/pyproject.toml` and add `"PyOpenGL>=3.1.7"` to the `dependencies` list so it reads:

```toml
dependencies = [
    "PySide6>=6.7",
    "PyOpenGL>=3.1.7"
]
```

Then reinstall to pick up the new dependency:

```bash
pip install -e ".[dev]"
```

Expected: pip downloads and installs PyOpenGL.

- [ ] **Step 2: Create `python/pluton/viewport/__init__.py`**

Write to `pluton/python/pluton/viewport/__init__.py`:

```python
"""Pluton 3D viewport components."""
```

- [ ] **Step 3: Create `python/pluton/viewport/viewport_widget.py`**

Write to `pluton/python/pluton/viewport/viewport_widget.py`:

```python
"""The 3D viewport widget — a QOpenGLWidget that draws via raw OpenGL.

For M0 this draws a single static triangle to verify the rendering pipeline.
In M1 this will be replaced with ModernGL-based rendering through a swappable
Renderer abstraction.
"""

import ctypes
from array import array

from OpenGL import GL
from PySide6.QtOpenGLWidgets import QOpenGLWidget


VERTEX_SHADER_SRC = """
#version 330 core

layout(location = 0) in vec2 in_position;
layout(location = 1) in vec3 in_color;

out vec3 v_color;

void main() {
    v_color = in_color;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_SRC = """
#version 330 core

in vec3 v_color;
out vec4 frag_color;

void main() {
    frag_color = vec4(v_color, 1.0);
}
"""

# Triangle vertices: (x, y, r, g, b) per vertex
TRIANGLE_VERTICES = array("f", [
    # x      y      r     g     b
     0.0,   0.6,   1.0,  0.0,  0.0,   # top vertex (red)
    -0.6,  -0.4,   0.0,  1.0,  0.0,   # bottom-left (green)
     0.6,  -0.4,   0.0,  0.0,  1.0,   # bottom-right (blue)
])


class ViewportWidget(QOpenGLWidget):
    """An OpenGL viewport. For M0, draws a static triangle."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._program: int = 0
        self._vao: int = 0
        self._vbo: int = 0

    def initializeGL(self) -> None:
        """Called once when the GL context is first created."""
        self._program = _compile_shader_program(VERTEX_SHADER_SRC, FRAGMENT_SHADER_SRC)
        self._vao, self._vbo = _create_triangle_buffers()
        GL.glClearColor(0.15, 0.15, 0.18, 1.0)

    def resizeGL(self, w: int, h: int) -> None:
        """Called when the widget is resized."""
        GL.glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        """Called each frame to redraw."""
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glUseProgram(self._program)
        GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)


def _compile_shader_program(vertex_src: str, fragment_src: str) -> int:
    """Compile a shader program from vertex and fragment sources.

    Raises RuntimeError if compilation or linking fails.
    """
    vertex_shader = _compile_shader(vertex_src, GL.GL_VERTEX_SHADER)
    fragment_shader = _compile_shader(fragment_src, GL.GL_FRAGMENT_SHADER)

    program = GL.glCreateProgram()
    GL.glAttachShader(program, vertex_shader)
    GL.glAttachShader(program, fragment_shader)
    GL.glLinkProgram(program)

    link_status = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
    if not link_status:
        log = GL.glGetProgramInfoLog(program).decode("utf-8", errors="replace")
        raise RuntimeError(f"Shader program link failed:\n{log}")

    GL.glDeleteShader(vertex_shader)
    GL.glDeleteShader(fragment_shader)
    return program


def _compile_shader(source: str, shader_type: int) -> int:
    """Compile a single shader. Raises RuntimeError on failure."""
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)

    compile_status = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS)
    if not compile_status:
        log = GL.glGetShaderInfoLog(shader).decode("utf-8", errors="replace")
        kind = "vertex" if shader_type == GL.GL_VERTEX_SHADER else "fragment"
        raise RuntimeError(f"{kind} shader compile failed:\n{log}")
    return shader


def _create_triangle_buffers() -> tuple[int, int]:
    """Create the VAO and VBO containing the triangle. Returns (vao, vbo)."""
    vao = GL.glGenVertexArrays(1)
    GL.glBindVertexArray(vao)

    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(
        GL.GL_ARRAY_BUFFER,
        TRIANGLE_VERTICES.tobytes(),
        GL.GL_STATIC_DRAW,
    )

    stride = 5 * ctypes.sizeof(ctypes.c_float)  # 5 floats per vertex
    # Attribute 0: position (vec2)
    GL.glEnableVertexAttribArray(0)
    GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
    # Attribute 1: color (vec3), offset by 2 floats
    GL.glEnableVertexAttribArray(1)
    GL.glVertexAttribPointer(
        1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
        ctypes.c_void_p(2 * ctypes.sizeof(ctypes.c_float)),
    )

    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
    GL.glBindVertexArray(0)
    return vao, vbo
```

**Note:** This file uses `PyOpenGL` (the `OpenGL` module) for the OpenGL calls because it's the standard Python OpenGL binding and avoids the larger ModernGL dependency for M0. We'll switch to ModernGL in M1 when we need its cleaner abstractions.

The `glBufferData` call uses PyOpenGL's three-argument form `(target, data, usage)` — PyOpenGL computes the size from the data buffer automatically.

- [ ] **Step 4: Update `python/pluton/ui/main_window.py` to embed the viewport**

Replace `python/pluton/ui/main_window.py` with:

```python
"""The main application window."""

from PySide6.QtWidgets import QMainWindow

from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        self._viewport = ViewportWidget(self)
        self.setCentralWidget(self._viewport)
```

- [ ] **Step 5: Verify the triangle renders**

From `pluton/`:

```bash
python -m pluton
```

Expected: A 1280x800 window opens. The central area is the viewport with a dark blue-grey background, containing a triangle with a red top vertex, green bottom-left, and blue bottom-right (smoothly interpolated colors between vertices).

If you see only the dark background and no triangle, the most likely causes are:
- Shader compile error (would raise RuntimeError on startup — check console)
- OpenGL context not 3.3+ (set Qt's default surface format earlier — see troubleshooting below)
- VBO bound incorrectly (recheck Step 2's bug fix)

**Troubleshooting — if the OpenGL context is too old:** Add this near the top of `python/pluton/app.py`, before `QApplication` is created:

```python
from PySide6.QtGui import QSurfaceFormat

fmt = QSurfaceFormat()
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
QSurfaceFormat.setDefaultFormat(fmt)
```

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/__init__.py python/pluton/viewport/viewport_widget.py python/pluton/ui/main_window.py pyproject.toml
git commit -m "feat(viewport): add QOpenGLWidget viewport rendering a colored triangle"
```

---

### Task 13: Add window smoke test

**Files:**
- Create: `pluton/tests/test_window.py`

- [ ] **Step 1: Write smoke test for the window**

Write to `pluton/tests/test_window.py`:

```python
"""Smoke tests that the window can be constructed without errors.

These tests use pytest-qt to provide a QApplication. They don't visually
verify rendering — that requires a more involved framebuffer-capture
approach which is out of scope for M0.
"""

import pytest


def test_main_window_constructs(qtbot):
    """The main window can be instantiated without raising."""
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Pluton"


def test_viewport_widget_constructs(qtbot):
    """The viewport widget can be instantiated without raising."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)

    # Widget exists and has the expected default size (Qt's default minimum)
    assert widget is not None
```

- [ ] **Step 2: Run the new tests**

```bash
pytest tests/test_window.py -v
```

Expected:
```
tests/test_window.py::test_main_window_constructs PASSED
tests/test_window.py::test_viewport_widget_constructs PASSED

2 passed
```

`pytest-qt` is already in the dev dependencies (it was added to `pyproject.toml` in Task 4).

- [ ] **Step 3: Run the full test suite to make sure everything still passes**

```bash
pytest -v
```

Expected: All Python tests (binding + window) pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_window.py
git commit -m "test: add smoke tests for main window and viewport widget"
```

---

### Task 14: Add clang-format and Ruff configuration verification

**Files:**
- Create: `pluton/.clang-format`

- [ ] **Step 1: Create `.clang-format`**

Write to `pluton/.clang-format`:

```yaml
---
Language: Cpp
BasedOnStyle: Google
IndentWidth: 4
TabWidth: 4
UseTab: Never
ColumnLimit: 100
PointerAlignment: Left
AlignAfterOpenBracket: Align
AllowShortFunctionsOnASingleLine: Empty
AllowShortIfStatementsOnASingleLine: false
BreakBeforeBraces: Attach
NamespaceIndentation: None
AccessModifierOffset: -4
```

- [ ] **Step 2: Format all C++ code (verifies the tool works)**

```bash
# From pluton/
clang-format -i cpp/include/pluton/*.h cpp/src/*.cpp cpp/bindings/*.cpp cpp/tests/*.cpp
```

- [ ] **Step 3: Format all Python code with Ruff**

```bash
ruff format python/ tests/
ruff check python/ tests/ --fix
```

Expected: No errors. Any formatting changes that occur are intentional.

- [ ] **Step 4: Verify nothing broke**

```bash
pytest -v
```

Expected: All tests still pass.

- [ ] **Step 5: Commit**

```bash
git add .clang-format cpp/ python/ tests/
git commit -m "chore: add .clang-format and apply Python + C++ formatting"
```

---

### Task 15: GitHub Actions CI for Windows and Linux

**Files:**
- Create: `pluton/.github/workflows/build.yml`

- [ ] **Step 1: Write the CI workflow**

Write to `pluton/.github/workflows/build.yml`:

```yaml
name: Build & Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    name: Build & Test (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-24.04, windows-2022]

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Ninja (Linux)
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y ninja-build

      - name: Install Ninja (Windows)
        if: runner.os == 'Windows'
        run: choco install ninja -y

      - name: Install Qt system dependencies (Linux only)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get install -y \
            libegl1 libgl1 libxkbcommon0 libdbus-1-3 \
            libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
            libxcb-image0 libxcb-shape0 libxkbcommon-x11-0 \
            libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 \
            libxcb-xkb1

      - name: Set up vcpkg
        uses: lukka/run-vcpkg@v11
        with:
          vcpkgGitCommitId: "2024.08.23"

      - name: Set CMAKE_TOOLCHAIN_FILE (Linux/macOS)
        if: runner.os != 'Windows'
        run: echo "CMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" >> $GITHUB_ENV

      - name: Set CMAKE_TOOLCHAIN_FILE (Windows)
        if: runner.os == 'Windows'
        run: echo "CMAKE_TOOLCHAIN_FILE=$env:VCPKG_ROOT\scripts\buildsystems\vcpkg.cmake" >> $env:GITHUB_ENV

      - name: Install Pluton (editable, with dev deps)
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run Python tests
        run: pytest -v

      - name: Configure C++ tests
        run: cmake -B build/tests -S . -G Ninja

      - name: Build C++ tests
        run: cmake --build build/tests

      - name: Run C++ tests
        working-directory: build/tests
        run: ctest --output-on-failure
```

Notes on choices:
- `vcpkgGitCommitId` pins the vcpkg version for reproducibility — pick the current latest release tag when you create the workflow.
- Linux needs a fairly long list of Qt's runtime dependencies; without them, PySide6 can't initialize a display. CI uses Xvfb-style headless display through Qt's offscreen platform — see next step.

- [ ] **Step 2: Configure Qt for headless CI**

CI runs without a real display. We need Qt to use its "offscreen" platform plugin during tests. Add this to `tests/conftest.py`:

Replace `tests/conftest.py` contents with:

```python
"""Shared pytest fixtures and configuration."""

import os
import sys

import pytest


# Ensure Qt uses the offscreen platform in CI / headless environments.
# This must run BEFORE QApplication is created (i.e., before any pytest-qt fixture).
if os.environ.get("CI") == "true" or os.environ.get("QT_QPA_PLATFORM"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

- [ ] **Step 3: Commit and push to trigger CI**

The remote was set up in Task 1, so this is just a commit + push:

```bash
git add .github/workflows/build.yml tests/conftest.py
git commit -m "ci: add GitHub Actions build & test workflow for Windows + Linux"
git push
```

Expected: the push triggers the workflow on `main`. GitHub Actions starts running the `Build & Test` jobs on Ubuntu and Windows.

- [ ] **Step 4: Verify both CI jobs go green**

Open `https://github.com/Parrow-Horrizon-Studio/pluton/actions` and watch the workflow run. Both `ubuntu-24.04` and `windows-2022` jobs should pass.

**If CI fails:** read the error log carefully. Common first-run CI issues:
- vcpkg pinned commit isn't valid → update to current vcpkg release tag
- Linux Qt deps missing → add the missing `apt-get` packages
- Windows Visual Studio toolchain not found → confirm `windows-2022` runner image is being used
- pytest-qt fails because Qt has no platform → confirm `QT_QPA_PLATFORM=offscreen` is being set

Iterate until green.

---

### Task 16: M0 sign-off

**Files:** None new — verification only.

- [ ] **Step 1: Run the full local test suite one more time**

```bash
pytest -v
cd build/tests && ctest --output-on-failure && cd ../..
```

Expected: All tests pass.

- [ ] **Step 2: Launch the app and visually verify the triangle**

```bash
python -m pluton
```

Expected: Window opens with the colored triangle visible.

- [ ] **Step 3: Verify CI is green on `main`**

Check `https://github.com/Parrow-Horrizon-Studio/pluton/actions` — most recent workflow run on `main` is green for both OS jobs.

- [ ] **Step 4: Tag the M0 release**

```bash
git tag -a v0.0.1-m0 -m "M0 — Foundation milestone complete"
git push --tags
```

**M0 is complete.** Pluton now has:
- Working Python ↔ C++ binding pipeline (nanobind)
- Cross-platform build (Windows + Linux via vcpkg + scikit-build-core)
- Qt window with embedded OpenGL viewport
- A rendered triangle (proving end-to-end rendering works)
- Python and C++ test suites
- GitHub Actions CI on both platforms
- Linting and formatting infrastructure

The foundation is laid for M1: core viewport with orbit/pan/zoom and a real 3D mesh.

---

## Notes for the Executing Engineer

- **Do not skip the TDD discipline** even when the tests feel trivial. The version test seems silly until you discover that the binding pipeline wasn't installing the compiled module into the right location — a test that imports and calls it catches this immediately.
- **Commit after every task.** Granular commits make bisecting and reverting trivial. Don't squash these — the history is genuinely useful for a foundational milestone.
- **If a task fails partway through, do not patch over it.** Stop, diagnose, fix the root cause, and retry. A flaky build at M0 will haunt the entire project.
- **The triangle in Task 12 is the visible payoff.** Treat the moment it appears on screen as the actual M0 success signal. Until then, you're working on faith.

---

## Self-Review Notes

A pass over the plan against the design doc's M0 scope:

| Design-doc M0 requirement | Covered by |
|---|---|
| Project scaffolding (cpp/python layout) | Tasks 1, 5, 7 |
| CMake | Tasks 2, 5, 10 |
| vcpkg | Tasks 3, 8, 10 |
| scikit-build-core | Task 4 |
| pyproject.toml | Task 4 |
| Qt window with QOpenGLWidget | Tasks 11, 12 |
| Draw a triangle | Task 12 |
| nanobind binding pipeline verified end-to-end | Tasks 5, 6, 8, 9 |
| CI green on Windows + Linux | Task 15 |
| pytest infrastructure | Task 9 |
| GoogleTest infrastructure | Task 10 |
| Linting/formatting | Task 14 |

All M0 scope items have an explicit task.

**Type / API consistency:** `pluton::version()` (C++) → `pluton._core.version()` (Python module) → `pluton.version` (top-level re-export). Same name throughout. The C++ header in Task 5 and the binding in Task 6 use identical signatures. Tests in Tasks 9 and 10 reference the same names.

**No placeholders:** every step has either code, exact commands, or a concrete action. The two intentional "TBD-ish" items (the choice of stricter shader version handling and ModernGL adoption) are both explicitly deferred to M1 with reasoning.

The plan is ready for execution.
