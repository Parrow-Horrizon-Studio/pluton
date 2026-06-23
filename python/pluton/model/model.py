from __future__ import annotations

import numpy as np

from pluton.model.definition import Definition
from pluton.model.instance import Instance
from pluton.model.material import MaterialLibrary
from pluton.model.tag import TagLibrary


class Model:
    """The scene graph: a root Definition + the active editing path."""

    def __init__(self) -> None:
        self._next_def_id = 0
        self._next_inst_id = 0
        self.root = self.new_definition("Model", is_group=False)
        self.active_path: list[Instance] = []
        self.materials = MaterialLibrary()
        self.tags = TagLibrary()

    # --- construction ---
    def new_definition(self, name: str, is_group: bool) -> Definition:
        d = Definition(self._next_def_id, name, is_group)
        self._next_def_id += 1
        return d

    def new_instance(self, definition: Definition, transform=None) -> Instance:
        inst = Instance(self._next_inst_id, definition, transform)
        self._next_inst_id += 1
        definition.instances.append(inst)
        return inst

    # --- active context ---
    @property
    def active_context(self) -> Definition:
        return self.active_path[-1].definition if self.active_path else self.root

    @property
    def active_scene(self):  # noqa: ANN201  (Scene)
        return self.active_context.mesh

    @property
    def active_world_transform(self) -> np.ndarray:
        m = np.eye(4, dtype=np.float64)
        for inst in self.active_path:
            m = m @ inst.transform
        return m

    def enter(self, instance: Instance) -> None:
        self.active_path.append(instance)

    def exit_one(self) -> None:
        if self.active_path:
            self.active_path.pop()

    def traverse(self):
        """Yield (definition, world_transform) depth-first from the root."""
        yield from self._traverse(self.root, np.eye(4, dtype=np.float64))

    def _traverse(self, definition, world):
        yield definition, world
        for inst in definition.children:
            yield from self._traverse(inst.definition, world @ inst.transform)

    def clone_definition(self, definition):
        """Deep-copy a definition's geometry + child instances into a fresh def."""
        clone = self.new_definition(definition.name, definition.is_group)
        idmap = {}
        for v in definition.mesh.vertices_iter():
            idmap[v.id] = clone.mesh.add_vertex(v.position)
        for e in definition.mesh.edges_iter():
            clone.mesh.add_edge(idmap[e.v1_id], idmap[e.v2_id])
        for f in definition.mesh.faces_iter():
            clone.mesh.add_face_from_loop([idmap[v] for v in f.loop_vertex_ids])
        for child in definition.children:
            new_child = self.new_instance(child.definition, child.transform)
            new_child.tag_id = child.tag_id
            clone.children.append(new_child)
        return clone

    def pick_instance(self, origin, direction):
        """Return the nearest Instance (among active context's children) hit by the ray.

        The world ray is transformed into each instance's local frame via mat_invert.
        Returns the Instance with the smallest hit.t, or None if no hit.
        """
        from pluton.geometry.transforms import mat_invert

        best, best_t = None, float("inf")
        world0 = self.active_world_transform
        for inst in self.active_context.children:
            world = world0 @ inst.transform
            inv = mat_invert(world)
            o = (inv @ np.append(origin, 1.0))[:3]
            d = inv[:3, :3] @ np.asarray(direction, np.float64)
            hit = inst.definition.mesh.ray_pick_face(o, d)
            if hit is not None and hit.t < best_t:
                best, best_t = inst, hit.t
        return best

    def revalidate_active_path(self) -> None:
        """Pop the active path to the nearest still-reachable instance.

        After an undo/redo destroys a group, the entered instance may no longer
        be a child of its parent context. Walk the path from the root; truncate
        at the first instance that isn't in its parent's children list.
        """
        valid: list[Instance] = []
        parent = self.root
        for inst in self.active_path:
            if inst in parent.children:
                valid.append(inst)
                parent = inst.definition
            else:
                break
        self.active_path = valid
