"""Loop-to-loop lofting, shared by Push/Pull, Offset and Follow Me.

All three tools perform the same operation with different destinations:
Push/Pull displaces the source loop along the face normal, Offset displaces
it along angle bisectors in plane, and Follow Me transforms a profile to
each station along a path. Only the destination positions differ, so the
stitching lives here.

Qt-free on purpose: this is the arithmetic most likely to be wrong, and it
must be testable without a QApplication.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
    DissolveEdgeCommand,
)


@dataclass(frozen=True, slots=True)
class LoftResult:
    """Commands already executed against the scene, plus the ids they created.

    `dst_vertex_ids` is parallel to the `src_loop_vids` passed in. Returning
    it is what lets callers stop reading AddVertexCommand._vertex_id.
    """

    commands: list
    dst_vertex_ids: list


def loft_between_loops(
    scene,
    src_loop_vids: Sequence[int],
    dst_positions: Sequence[np.ndarray],
    *,
    cap_start: bool,
    cap_end: bool,
) -> LoftResult:
    """Stitch a ring of quads between `src_loop_vids` and new vertices at
    `dst_positions`, executing each command as it is built.

    Commands are executed here, not by the caller: every caller pushes the
    finished CompositeCommand with push_executed, so the scene must already
    reflect the change.

    `cap_start` closes the source end with the source loop REVERSED, so its
    normal points opposite the sweep. `cap_end` closes the destination end
    in source winding. Two flags rather than one because the callers need
    three different answers: Push/Pull always caps the far end and caps the
    near end only for a standalone source, Follow Me caps both ends of an
    open path, and a closed path caps neither.
    """
    n = len(src_loop_vids)
    assert n == len(dst_positions), "loop and destination lengths must match"

    commands: list = []

    dst_vert_cmds: list[AddVertexCommand] = []
    for pos in dst_positions:
        c = AddVertexCommand(np.asarray(pos, dtype=np.float32))
        c.do(scene)
        dst_vert_cmds.append(c)
        commands.append(c)
    # AddVertexCommand has no public accessor for the id it allocated (kept
    # private per this milestone's resolution: scene_commands.py is touched
    # by other tasks and widening its API is out of scope). This matches the
    # shipped Push/Pull code's own reach-in.
    dst_vids = [c._vertex_id for c in dst_vert_cmds]  # type: ignore[attr-defined]

    for src_vid, dst_vid in zip(src_loop_vids, dst_vids, strict=True):
        c = AddEdgeCommand(src_vid, dst_vid)
        c.do(scene)
        commands.append(c)

    for i in range(n):
        c = AddEdgeCommand(dst_vids[i], dst_vids[(i + 1) % n])
        c.do(scene)
        commands.append(c)

    for i in range(n):
        a = src_loop_vids[i]
        b = src_loop_vids[(i + 1) % n]
        c = AddFaceCommand((a, b, dst_vids[(i + 1) % n], dst_vids[i]))
        c.do(scene)
        commands.append(c)

    if cap_end:
        c = AddFaceCommand(tuple(dst_vids))
        c.do(scene)
        commands.append(c)

    if cap_start:
        c = AddFaceCommand(tuple(reversed(list(src_loop_vids))))
        c.do(scene)
        commands.append(c)

    return LoftResult(commands=commands, dst_vertex_ids=dst_vids)


def seam_merge(scene, candidate_edges: Sequence[int]) -> list:
    """Dissolve candidate edges whose two incident faces are coplanar.

    Single pass over the candidates only. Callers capture them BEFORE
    removing a source face, because removal invalidates the boundary.
    """
    out: list = []
    for e in candidate_edges:
        if not scene.edge_is_live(e):
            continue
        f_a, f_b = scene.edge_faces(e)
        if f_a is None or f_b is None:
            continue
        if scene.faces_are_coplanar(f_a, f_b):
            cmd = DissolveEdgeCommand(e)
            cmd.do(scene)
            out.append(cmd)
    return out
