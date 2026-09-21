"""Unit tests for the snap & inference engine (3D, screen-space)."""

from __future__ import annotations

import numpy as np


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    return cam


def _screen_of(cam, world):
    """Pixel coords that project onto `world` in a 1280x800 viewport."""
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), 1280, 800)
    return (sx, sy)


def test_endpoint_snap_in_3d_off_the_ground():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    vid = scene.add_vertex(np.array([1.0, 2.0, 3.0], dtype=np.float32))  # off-ground
    cam = _camera_at_default()
    cursor = _screen_of(cam, [1.0, 2.0, 3.0])
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ENDPOINT
    assert res.vertex_id == vid
    np.testing.assert_allclose(res.world_position, scene.vertex(vid).position, atol=1e-4)


def test_midpoint_snap_in_3d():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([0.0, 4.0, 2.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 2.0, 2.0])  # the midpoint
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.MIDPOINT
    assert res.edge_id == e
    assert abs(res.edge_t - 0.5) < 1e-3
    np.testing.assert_allclose(res.world_position, [0.0, 2.0, 2.0], atol=1e-3)


def test_grid_fallback_on_empty_ground():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    cursor = _screen_of(cam, [2.3, -1.4, 0.0])
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.GRID
    np.testing.assert_allclose(res.world_position, [2.0, -1.0, 0.0], atol=1e-3)


def test_grid_fallback_lands_on_a_rotated_translated_contexts_own_floor():
    """The grid fallback used to build [gx, gy, 0.0] in WORLD space regardless
    of the active transform (`world_transform`), by intersecting the cursor
    ray with the WORLD Z=0 plane. Inside a context rotated and translated
    away from that plane, the correct floor is the context's own LOCAL Z=0,
    which the fix reaches by intersecting the already-available
    `ray_origin_local` / `ray_dir_local` instead.

    Fixture: a context rotated 35 degrees about world Z and translated up by
    4 world units. Because the rotation axis IS the world Z axis, the
    context's local floor is still a flat (unrotated-in-tilt) plane, just
    spun and raised -- which makes the expected answer exact to compute
    independently: pick a local grid point, rotate+translate it forward to
    get the world point the user's cursor is aimed at, and assert the snap
    reproduces that same world point (not the unrotated world floor at Z=0,
    which is where the pre-fix code would land it).
    """
    import math

    from pluton.geometry.transforms import apply_mat, mat_compose, mat_rotate, mat_translate
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()

    rot = mat_rotate([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], math.radians(35.0))
    trans = mat_translate([0.0, 0.0, 4.0])
    wt = mat_compose(rot, trans)

    # An on-grid point in the context's LOCAL frame (already an integer, so
    # GRID_SIZE_WORLD=1.0 rounding is a no-op and the expectation is exact).
    local_point = np.array([2.0, -1.0, 0.0], dtype=np.float64)
    world_point = apply_mat(local_point, wt)[0]

    cursor = _screen_of(cam, world_point)
    res = eng.snap(cursor, (1280, 800), cam, scene, world_transform=wt)

    assert res.kind == SnapKind.GRID
    np.testing.assert_allclose(res.world_position, world_point, atol=1e-3)
    # The pre-fix behaviour intersected WORLD Z=0 and returned a literal
    # world z=0.0 -- clearly distinct from this context's floor at world z=4.
    assert abs(float(res.world_position[2]) - 4.0) < 1e-2


def test_none_when_scene_is_none():
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    cam = _camera_at_default()
    res = eng.snap((640.0, 400.0), (1280, 800), cam, None)  # type: ignore[arg-type]
    assert res.kind == SnapKind.NONE


def test_selection_prefers_precedence_then_depth():
    from pluton.viewport.snap_engine import SnapEngine, SnapKind, _Candidate

    eng = SnapEngine()
    near = np.zeros(3, dtype=np.float32)
    cands = [
        _Candidate(SnapKind.ON_FACE, near, screen_dist=1.0, depth=5.0, label="f"),
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=3.0, depth=9.0, label="e"),
        _Candidate(SnapKind.MIDPOINT, near, screen_dist=2.0, depth=1.0, label="m"),
    ]
    chosen = eng._select(cands)
    assert chosen.kind == SnapKind.ENDPOINT  # precedence beats smaller screen_dist

    two = [
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=2.0, depth=9.0, label="far"),
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=2.0, depth=2.0, label="near"),
    ]
    assert eng._select(two).label == "near"


def test_closest_points_two_lines_perpendicular_crossing():
    from pluton.viewport.snap_engine import _closest_points_two_lines

    p1 = np.array([0, 0, 0], np.float32); d1 = np.array([1, 0, 0], np.float32)
    p2 = np.array([3, 0, 1], np.float32); d2 = np.array([0, 1, 0], np.float32)
    _, _, c1, c2 = _closest_points_two_lines(p1, d1, p2, d2)
    np.testing.assert_allclose(c1, [3, 0, 0], atol=1e-5)
    np.testing.assert_allclose(c2, [3, 0, 1], atol=1e-5)


def test_closest_point_on_segment_to_ray_clamps():
    from pluton.viewport.snap_engine import _closest_point_on_segment_to_ray

    ro = np.array([5, 0, 10], np.float32); rd = np.array([0, 0, -1], np.float32)
    a = np.array([0, 0, 0], np.float32); b = np.array([2, 0, 0], np.float32)
    pt, t = _closest_point_on_segment_to_ray(ro, rd, a, b)
    np.testing.assert_allclose(pt, [2, 0, 0], atol=1e-5)  # clamped to far endpoint
    assert t == 1.0


def test_precedence_rank_orders_endpoint_above_on_face():
    from pluton.viewport.snap_engine import SnapKind, _PRECEDENCE_RANK

    assert _PRECEDENCE_RANK[SnapKind.ENDPOINT] < _PRECEDENCE_RANK[SnapKind.MIDPOINT]
    assert _PRECEDENCE_RANK[SnapKind.MIDPOINT] < _PRECEDENCE_RANK[SnapKind.ON_EDGE]
    assert _PRECEDENCE_RANK[SnapKind.ON_EDGE] < _PRECEDENCE_RANK[SnapKind.ON_FACE]
    assert _PRECEDENCE_RANK[SnapKind.ON_FACE] < _PRECEDENCE_RANK[SnapKind.GRID]
    assert _PRECEDENCE_RANK[SnapKind.INTERSECTION] < _PRECEDENCE_RANK[SnapKind.MIDPOINT]


def test_on_edge_snap_to_interior_point():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 2.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [1.0, 0.0, 2.0])  # quarter point, far from midpoint(2,0,2)
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ON_EDGE
    assert res.edge_id == e
    assert abs(res.edge_t - 0.25) < 5e-2
    np.testing.assert_allclose(res.world_position, [1.0, 0.0, 2.0], atol=5e-2)


def test_on_face_snap_over_a_face():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([-1.0, -1.0, 1.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, -1.0, 1.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 1.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([-1.0, 1.0, 1.0], dtype=np.float32))
    for a, b in [(v0, v1), (v1, v2), (v2, v3), (v3, v0)]:
        scene.add_edge(a, b)
    f = scene.add_face_from_loop([v0, v1, v2, v3])
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 0.0, 1.0])  # face center
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ON_FACE
    assert res.face_id == f
    np.testing.assert_allclose(res.world_position[2], 1.0, atol=1e-3)


def test_endpoint_beats_midpoint_full_pipeline():
    """Full-pipeline precedence (not just _select): a vertex under the cursor
    wins over the edge's midpoint/on-edge candidates."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([0.0, 0.3, 2.0], dtype=np.float32))  # short edge
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 0.0, 2.0])  # exactly on v0
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ENDPOINT
    assert res.vertex_id == v0


def test_axis_lock_vertical_z_in_3d():
    """Z-axis lock — impossible in M2's ground-only world."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    cursor = _screen_of(cam, [0.0, 0.0, 3.0])  # straight up the blue axis
    res = eng.snap(cursor, (1280, 800), cam, scene, anchor=anchor)
    assert res.kind == SnapKind.AXIS_LOCK
    assert res.axis == 2  # Z / blue
    np.testing.assert_allclose(res.world_position, [0.0, 0.0, 3.0], atol=5e-2)


def test_intersection_of_axis_line_and_edge():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    # Edge crosses the X axis at (3,0,0) at parameter t=0.25 (NOT its midpoint).
    v0 = scene.add_vertex(np.array([3.0, -1.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([3.0, 3.0, 0.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)  # draw along +X from origin
    cursor = _screen_of(cam, [3.0, 0.0, 0.0])
    res = eng.snap(cursor, (1280, 800), cam, scene, anchor=anchor)
    assert res.kind == SnapKind.INTERSECTION
    assert res.edge_id == e
    np.testing.assert_allclose(res.world_position, [3.0, 0.0, 0.0], atol=5e-2)


def test_axis_lock_wins_over_a_face():
    """Axis lock must be reachable while the cursor is over a face.

    Regression test for the M7.6b section 1 finding: ON_FACE's candidate is
    always in tolerance (its position is the ray-face hit, so it reprojects onto
    the cursor exactly), and ON_FACE outranked AXIS_LOCK, so the axis inference
    was invisible in the ordinary case of drawing on a face.
    """
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    vids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    ]
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        scene.add_edge(vids[a], vids[b])
    scene.add_face_from_loop(vids)

    cam = _camera_at_default()
    anchor = np.array([2.0, 2.0, 0.0], dtype=np.float32)
    # A point on the red axis through the anchor, comfortably inside the quad
    # and away from every vertex, midpoint and boundary edge.
    probe = np.array([6.0, 2.0, 0.0], dtype=np.float32)
    cursor = _screen_of(cam, probe)

    res = SnapEngine().snap(cursor, (1280, 800), cam, scene, anchor=anchor)
    assert res.kind == SnapKind.AXIS_LOCK, f"expected AXIS_LOCK, got {res.kind}"
    assert res.axis == 0, "expected the red (X) axis"
    # The face is still reported, so a shape started here lands on the quad.
    assert res.face_id is not None


def test_axis_candidates_skips_a_ray_collinear_with_its_axis():
    """#31: `closest_points_two_lines`' solve divides by
    |ray_dir x axis_dir|^2, proportional to sin^2 of the angle between the
    cursor ray and the axis direction. That collapses toward zero exactly
    when the ray runs parallel (collinear) to the axis -- e.g. a view nearly
    end-on down that axis -- and a sub-degree wobble in the cursor ray then
    swings the reported axis point by hundreds of world units.

    Builds a ray within 0.5 degrees of the red (X) axis and hands back, as
    the cursor, the exact screen projection the UNGUARDED solve's own result
    would land on -- guaranteeing that result would read as "under the
    cursor" (distance 0) if the guard did not skip it first.
    """
    import math

    from pluton.geometry.ray import closest_points_two_lines
    from pluton.viewport.snap_candidates import axis_candidates

    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)

    theta = math.radians(0.5)  # within the 1-degree guard
    ray_dir = np.array([math.cos(theta), math.sin(theta), 0.0], dtype=np.float64)
    ray_origin = np.array([2.0, 3.0, 5.0], dtype=np.float64)

    _, _, _c_ray, c_axis_red = closest_points_two_lines(
        ray_origin, ray_dir, anchor, np.array([1.0, 0.0, 0.0], dtype=np.float32)
    )
    proj = cam.world_to_screen(c_axis_red, 1280, 800)
    assert proj is not None, "fixture's ill-conditioned point must still project"
    px, py, _ = proj

    out = axis_candidates(px, py, 1280, 800, cam, anchor, ray_origin, ray_dir, 8.0)
    red_candidates = [c for c in out if c.axis == 0]
    assert red_candidates == [], (
        f"expected the near-collinear red axis to be skipped, got {red_candidates}"
    )


def test_same_kind_tiebreak_prefers_the_candidate_under_the_cursor():
    """#31: two endpoints in tolerance must resolve to the nearer one on screen.

    The far vertex is placed NEARER the camera, so a depth-only tiebreak picks it.
    """
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    scene = Scene()
    cam = _camera_at_default()

    under_cursor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    v_far = scene.add_vertex(under_cursor)
    cursor = _screen_of(cam, under_cursor)

    # Walk a second vertex toward the camera until it projects a few pixels off
    # the cursor while sitting at a smaller depth.
    v_near = None
    for step in np.linspace(0.05, 2.0, 80):
        cand = under_cursor + np.array([0.0, 0.0, step], dtype=np.float32)
        proj = cam.world_to_screen(cand, 1280, 800)
        if proj is None:
            continue
        dist = float(np.hypot(proj[0] - cursor[0], proj[1] - cursor[1]))
        if 2.0 < dist < 7.0:
            v_near = scene.add_vertex(cand)
            break
    assert v_near is not None, "fixture failed to place a second endpoint in tolerance"

    res = SnapEngine().snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ENDPOINT
    assert res.vertex_id == v_far, "expected the endpoint under the cursor, not the nearer one"
