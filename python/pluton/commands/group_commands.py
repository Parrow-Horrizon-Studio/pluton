from __future__ import annotations

import numpy as np

from pluton.commands.command import Command


class MakeGroupCommand(Command):
    """Lift selected entities from a parent definition into a new Definition+Instance."""

    name = "Make Group"

    def __init__(self, parent_definition, vertex_ids, edge_ids, face_ids,
                 *, is_group: bool = True, name: str | None = None) -> None:
        self._parent = parent_definition
        self._vids = list(vertex_ids)
        self._eids = list(edge_ids)
        self._fids = list(face_ids)
        self._is_group = is_group
        self._name = name
        self.created_instance = None
        self._captured = None  # (verts, edges, faces) descriptors for undo

    def do(self, model) -> None:  # noqa: ANN001
        parent_scene = self._parent.mesh
        # 1. Capture lifted geometry descriptors (original ids) for undo restore.
        verts = [(v, parent_scene.vertex(v).position.copy()) for v in self._vids]

        # Collect edges: explicitly-provided ids PLUS boundary edges of lifted faces
        # (auto-inserted by add_face_from_loop and not present in _eids).
        edge_id_set: set[int] = set(self._eids)
        for f in self._fids:
            for e in parent_scene.face_edges(f):
                edge_id_set.add(e)
        all_edge_ids = sorted(edge_id_set)
        edges = [(e, parent_scene.edge(e).v1_id, parent_scene.edge(e).v2_id)
                 for e in all_edge_ids]

        faces = [(f, tuple(parent_scene.face(f).loop_vertex_ids)) for f in self._fids]
        self._captured = (verts, edges, faces)

        # 2. Create the definition + copy geometry into it (fresh ids in child mesh).
        defn = model.new_definition(
            self._name or (f"Group #{model._next_def_id}" if self._is_group
                           else f"Component #{model._next_def_id}"),
            is_group=self._is_group,
        )
        idmap = {}
        for v, pos in verts:
            idmap[v] = defn.mesh.add_vertex(pos)
        for _e, v1, v2 in edges:
            defn.mesh.add_edge(idmap[v1], idmap[v2])
        for _f, loop in faces:
            defn.mesh.add_face_from_loop([idmap[v] for v in loop])

        # 3. Remove lifted geometry from the parent (faces, then edges, then verts).
        for f, _loop in faces:
            parent_scene.remove_face(f)
        for e, _v1, _v2 in edges:
            try:
                parent_scene.remove_edge(e)
            except Exception:
                pass  # edge may have been auto-removed with its faces
        for v, _pos in verts:
            try:
                parent_scene.remove_vertex(v)
            except Exception:
                pass

        # 4. Create one instance in the parent.
        inst = model.new_instance(defn)
        self._parent.children.append(inst)
        self.created_instance = inst

    def undo(self, model) -> None:  # noqa: ANN001
        parent_scene = self._parent.mesh
        verts, edges, faces = self._captured
        # Remove the instance + definition.
        if self.created_instance in self._parent.children:
            self._parent.children.remove(self.created_instance)
        # Restore parent geometry by original ids (verts first, then edges, then faces).
        for v, pos in verts:
            parent_scene.restore_vertex(v, pos)
        for e, v1, v2 in edges:
            parent_scene.restore_edge(e, v1, v2)
        for f, loop in faces:
            parent_scene.restore_face(f, loop)


class MakeComponentCommand(MakeGroupCommand):
    name = "Make Component"

    def __init__(self, parent_definition, vertex_ids, edge_ids, face_ids, *, name: str) -> None:
        super().__init__(parent_definition, vertex_ids, edge_ids, face_ids,
                         is_group=False, name=name)
