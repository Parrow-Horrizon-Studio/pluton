"""Pure selection derivations: the neighbour queries behind smart-select, the
connected-component flood behind triple-click, and the set operations behind
Edit > Invert and the right-click Select submenu.

Every function takes ids plus a Scene (or, where tags are involved, a Model)
and returns ids. Nothing here imports Qt, mutates a Selection, or knows that
menus exist, so each function is directly callable in a test with no widget
and no QApplication.

That is deliberate rather than stylistic. M7.6b measured that tests routed
through the widget masked defects which direct calls on the pure generators
caught, and the same milestone shipped one constant in three copies because
two callers each grew their own. Triple-click and `grow` share a walk here
for the same reason: one copy cannot drift.

A dead id is skipped rather than raised on, matching how
`transform_support.selection_vertices` already tolerates a stale id. A
selection can outlive the geometry it names, briefly, between a command and
the `prune_to_live` that follows it.
"""

from __future__ import annotations

from collections import deque


def bounding_edges(scene, face_ids) -> set[int]:
    """Every edge on the boundary loop of any face in `face_ids`.

    This is the second half of a double-click on a face: the face itself plus
    what bounds it.
    """
    out: set[int] = set()
    for f_id in face_ids:
        try:
            loop_edges = scene.face_edges(f_id)
        except KeyError:
            continue
        out.update(int(e) for e in loop_edges)
    return out


def adjacent_faces(scene, edge_ids) -> set[int]:
    """Every face on either side of any edge in `edge_ids`.

    `Scene.edge_faces` returns a two-tuple whose entries are None where the
    edge is naked on that side, so both are filtered rather than assumed
    present. A wholly naked edge contributes nothing.
    """
    out: set[int] = set()
    for e_id in edge_ids:
        try:
            side_a, side_b = scene.edge_faces(e_id)
        except KeyError:
            continue
        if side_a is not None:
            out.add(int(side_a))
        if side_b is not None:
            out.add(int(side_b))
    return out


def incident_edges(scene, vertex_ids) -> set[int]:
    """Every live edge with one of `vertex_ids` as an endpoint.

    There is no vertex-to-edge index on Scene, so this scans `edges_iter`.
    That is the same scan `pick_selectable` already performs on every pick,
    so it is not a new cost class.
    """
    wanted = {int(v) for v in vertex_ids}
    if not wanted:
        return set()
    return {
        int(e.id) for e in scene.edges_iter() if int(e.v1_id) in wanted or int(e.v2_id) in wanted
    }


def connected_component(scene, seed_vertex_ids) -> tuple[set[int], set[int], set[int]]:
    """Flood from `seed_vertex_ids` across shared vertices.

    Returns `(vertices, edges, faces)`. An edge is included when BOTH its
    endpoints are reached; a face when its WHOLE loop is reached. Both follow
    from the walk rather than being separate rules: an edge with one endpoint
    reached would mean the other endpoint was reachable too, so the stricter
    test is the honest one and it keeps the result symmetric.

    Connectivity is through shared vertices, not shared edges (spec 2.4).
    Two faces meeting at a single corner are one component. That is what makes
    the result independent of which entity kind seeded the walk, which is in
    turn what lets double-click and triple-click compose.

    This is the walk `follow_me_tool._order_path` performs over a selected
    edge set, lifted so there is one copy. That caller keeps its own version
    for now: it needs fork detection and an ORDERED chain, which this does not
    produce.
    """
    adjacency: dict[int, set[int]] = {}
    edges_by_pair: dict[tuple[int, int], int] = {}
    for e in scene.edges_iter():
        v1, v2 = int(e.v1_id), int(e.v2_id)
        adjacency.setdefault(v1, set()).add(v2)
        adjacency.setdefault(v2, set()).add(v1)
        edges_by_pair[(min(v1, v2), max(v1, v2))] = int(e.id)

    seeds = {int(v) for v in seed_vertex_ids if int(v) in adjacency}
    if not seeds:
        return set(), set(), set()

    reached: set[int] = set(seeds)
    queue = deque(seeds)
    while queue:
        v = queue.popleft()
        for n in adjacency[v]:
            if n not in reached:
                reached.add(n)
                queue.append(n)

    edges = {e_id for (v1, v2), e_id in edges_by_pair.items() if v1 in reached and v2 in reached}

    faces: set[int] = set()
    for f in scene.faces_iter():
        loop = scene.face_loop(f.id)
        if loop and all(int(v) in reached for v in loop):
            faces.add(int(f.id))

    return reached, edges, faces
