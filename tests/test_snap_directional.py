"""Parallel, Perpendicular and From-Point inference against an acquired reference."""

from __future__ import annotations

import numpy as np


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    return cam


def _screen_of(cam, world):
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), 1280, 800)
    return (sx, sy)


def _acquired_edge(position, direction):
    from pluton.viewport.inference import Acquired, AcquiredKind

    d = np.asarray(direction, dtype=np.float64)
    return Acquired(
        kind=AcquiredKind.EDGE,
        position=np.asarray(position, dtype=np.float64),
        direction=d / float(np.linalg.norm(d)),
        entity_id=0,
    )


def _acquired_vertex(position):
    from pluton.viewport.inference import Acquired, AcquiredKind

    return Acquired(
        kind=AcquiredKind.VERTEX,
        position=np.asarray(position, dtype=np.float64),
        direction=None,
        entity_id=0,
    )


def test_parallel_to_an_acquired_edge():
    """An edge running 1,1,0 gives a parallel inference along 1,1,0 from the anchor."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    acquired = _acquired_edge((5.0, 5.0, 0.0), (1.0, 1.0, 0.0))

    # A point on the parallel line through the anchor.
    probe = np.array([2.0, 2.0, 0.0], dtype=np.float32)
    res = SnapEngine().snap(
        _screen_of(cam, probe), (1280, 800), cam, scene, anchor=anchor, acquired=acquired
    )
    assert res.kind == SnapKind.PARALLEL, f"got {res.kind}"
    np.testing.assert_allclose(res.world_position, probe, atol=1e-3)


def test_perpendicular_resolves_in_the_drawing_plane():
    """Perpendicular to a 1,0,0 edge in the Z-normal plane runs along 0,1,0."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    acquired = _acquired_edge((3.0, 0.0, 0.0), (1.0, 0.0, 0.0))

    probe = np.array([0.0, 3.0, 0.0], dtype=np.float32)
    res = SnapEngine().snap(
        _screen_of(cam, probe),
        (1280, 800),
        cam,
        scene,
        anchor=anchor,
        acquired=acquired,
        plane_normal=np.array([0.0, 0.0, 1.0]),
    )
    assert res.kind == SnapKind.PERPENDICULAR, f"got {res.kind}"
    np.testing.assert_allclose(res.world_position, probe, atol=1e-3)


def test_perpendicular_is_skipped_when_the_edge_runs_along_the_plane_normal():
    """cross(n, d) degenerates, so no candidate is offered rather than a guess."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    acquired = _acquired_edge((0.0, 0.0, 3.0), (0.0, 0.0, 1.0))

    probe = np.array([0.0, 3.0, 0.0], dtype=np.float32)
    res = SnapEngine().snap(
        _screen_of(cam, probe),
        (1280, 800),
        cam,
        scene,
        anchor=anchor,
        acquired=acquired,
        plane_normal=np.array([0.0, 0.0, 1.0]),
    )
    assert res.kind != SnapKind.PERPENDICULAR


def test_from_point_radiates_axes_from_an_acquired_vertex():
    """A point on the red axis THROUGH THE ACQUIRED VERTEX, not through the anchor."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    acquired = _acquired_vertex((0.0, 4.0, 0.0))

    probe = np.array([3.0, 4.0, 0.0], dtype=np.float32)  # on X through (0,4,0)
    res = SnapEngine().snap(
        _screen_of(cam, probe), (1280, 800), cam, scene, anchor=anchor, acquired=acquired
    )
    assert res.kind == SnapKind.FROM_POINT, f"got {res.kind}"
    assert res.axis == 0
    np.testing.assert_allclose(res.world_position, probe, atol=1e-3)


def test_no_acquisition_yields_no_directional_candidates():
    """The pre-M7.6b path must be unchanged when nothing is acquired."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    probe = np.array([2.0, 2.0, 0.0], dtype=np.float32)

    res = SnapEngine().snap(_screen_of(cam, probe), (1280, 800), cam, scene, anchor=anchor)
    assert res.kind not in (SnapKind.PARALLEL, SnapKind.PERPENDICULAR, SnapKind.FROM_POINT)
