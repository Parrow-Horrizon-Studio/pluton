from __future__ import annotations

import pluton.ui.main_window as mw_mod
from pluton.ui.main_window import MainWindow


def _win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_menu_has_gltf_actions(qtbot):
    w = _win(qtbot)
    labels = [a.text() for a in w._file_menu.actions()]
    assert any("glTF" in t and "Import" in t for t in labels)
    assert any("glTF" in t and "Export" in t for t in labels)


def test_export_gltf_calls_export(qtbot, monkeypatch, tmp_path):
    w = _win(qtbot)
    w._prompt_save_path = lambda *a, **k: str(tmp_path / "m.glb")
    called = {}
    monkeypatch.setattr(mw_mod, "export_gltf",
                        lambda model, path: called.setdefault("path", path))
    w._on_export_gltf()
    assert called["path"].endswith(".glb")


def test_import_gltf_cancelled_is_noop(qtbot):
    w = _win(qtbot)
    w._prompt_open_path = lambda *a, **k: None
    w._on_import_gltf()   # must not raise


def test_import_gltf_runs_command(qtbot, monkeypatch, tmp_path):
    from pluton.io.gltf_scene import GltfMesh, GltfNode, GltfSceneData
    tri = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    ident = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    scene = GltfSceneData(
        nodes=(GltfNode(name="A", parent=-1, transform=ident, mesh_indices=(0,)),),
        meshes=(GltfMesh(positions=tri, triangles=((0, 1, 2),), material_index=-1),),
        materials=(),
    )
    w = _win(qtbot)
    w._prompt_open_path = lambda *a, **k: str(tmp_path / "m.glb")
    monkeypatch.setattr(mw_mod, "read_gltf_scene", lambda path: scene)
    before = len(w._model.active_context.children)
    w._on_import_gltf()
    assert len(w._model.active_context.children) == before + 1
