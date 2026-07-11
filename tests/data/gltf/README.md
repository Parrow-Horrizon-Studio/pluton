# glTF test fixtures (M6c)

- **plain_box.glb** — a minimal uncompressed unit-cube GLB, generated
  programmatically for Pluton's tests (no third-party content).
- **draco_box.glb** — the Khronos **Box** sample with
  `KHR_draco_mesh_compression`, packed from the `glTF-Draco` variant
  (`Box.gltf` + `Box.bin`) into a single self-contained `.glb`.
  Source: <https://github.com/KhronosGroup/glTF-Sample-Assets> (Models/Box).
  License: **CC0 1.0 (public domain)** — Khronos sample asset.

`draco_box.glb` is the fixture behind the permanent Draco CI gate: it must
decode on every run, guarding that the Assimp dependency still provides Draco
support.
