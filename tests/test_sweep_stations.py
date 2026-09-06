"""Path stations, miters, and the refusal test (M7.4 Task 7)."""

from __future__ import annotations

import numpy as np
import pytest
from pluton.tools.sweep_support import SweepRefused, sweep_stations

UNIT_SQUARE = np.array(
    [[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0], [0.5, 0.5, 0.0], [-0.5, 0.5, 0.0]],
    dtype=np.float64,
)


def test_a_straight_path_gives_one_station_per_point():
    path = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64)
    stations = sweep_stations(UNIT_SQUARE, path, closed=False)
    assert len(stations) == 3
    assert stations[0].shape == (4, 4)


def test_a_closed_path_wraps_without_duplicating_a_station():
    square_path = np.array(
        [[0, 0, 0], [4, 0, 0], [4, 4, 0], [0, 4, 0]], dtype=np.float64
    )
    stations = sweep_stations(UNIT_SQUARE, square_path, closed=True)
    assert len(stations) == 4


def test_a_right_angle_miters_rather_than_gapping():
    # The station at the corner must bisect, so its plane normal is 45
    # degrees from both segments rather than aligned with either.
    path = np.array([[0, 0, 0], [4, 0, 0], [4, 4, 0]], dtype=np.float64)
    stations = sweep_stations(UNIT_SQUARE, path, closed=False)
    corner_normal = stations[1][:3, 2]
    seg_in = np.array([1.0, 0.0, 0.0])
    seg_out = np.array([0.0, 1.0, 0.0])
    assert abs(np.dot(corner_normal, seg_in)) == pytest.approx(
        abs(np.dot(corner_normal, seg_out)), abs=1e-9
    )


def test_a_corner_too_tight_for_the_profile_is_refused():
    # A hairpin: the profile is 1 wide, the turn doubles back, so the
    # mitered plane inverts the profile.
    big_profile = UNIT_SQUARE * 10.0
    path = np.array([[0, 0, 0], [1, 0, 0], [0.02, 0.01, 0]], dtype=np.float64)
    with pytest.raises(SweepRefused):
        sweep_stations(big_profile, path, closed=False)


def test_refusal_names_the_offending_corner():
    big_profile = UNIT_SQUARE * 10.0
    path = np.array([[0, 0, 0], [1, 0, 0], [0.02, 0.01, 0]], dtype=np.float64)
    with pytest.raises(SweepRefused) as exc:
        sweep_stations(big_profile, path, closed=False)
    assert "corner" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Additional discrimination tests (not in the task brief).
#
# The brief's own tests use a symmetric square profile and, mostly,
# symmetric turns -- exactly the trap the task calls out: a wrong rotation
# is easy to hide behind that symmetry. These use an off-centre, asymmetric
# profile and check actual transformed positions/orientations, not just
# station counts.
# ---------------------------------------------------------------------------

# An asymmetric, off-centre right triangle: no symmetry to hide a wrong
# rotation or a "translate only" implementation behind.
_TRIANGLE = np.array(
    [[1.0, 0.0, 0.0], [3.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=np.float64
)


def _apply(station: np.ndarray, point: np.ndarray) -> np.ndarray:
    h = np.array([point[0], point[1], point[2], 1.0])
    return (station @ h)[:3]


def test_straight_sweep_actually_rotates_an_off_axis_profile():
    # Catches "returning positions dressed as transforms": a naive
    # implementation that only translates (never rotates) the profile
    # would place _TRIANGLE's vertices unchanged in x/y at every station.
    # Sweeping along +X, the profile plane must turn 90 degrees to face
    # the path, so the correct transform moves this vertex off the z=0
    # plane the profile started on.
    path = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]], dtype=np.float64)
    stations = sweep_stations(_TRIANGLE, path, closed=False)

    centroid = _TRIANGLE.mean(axis=0)
    r = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])  # normal(0,0,1) -> (1,0,0)
    expected = path[0] + r @ (_TRIANGLE[0] - centroid)

    got = _apply(stations[0], _TRIANGLE[0])
    assert got == pytest.approx(expected, abs=1e-9)
    # A translate-only implementation would leave the z-component at 0.
    assert got[2] != pytest.approx(0.0, abs=1e-6)


def test_every_station_places_the_profile_centroid_on_the_path():
    # True at every station regardless of corner tightness or winding --
    # the plane always passes through the path point.
    path = np.array(
        [[0, 0, 0], [3, 0, 0], [3, 3, 0], [3, 3, 5]], dtype=np.float64
    )
    stations = sweep_stations(_TRIANGLE, path, closed=False)
    centroid = _TRIANGLE.mean(axis=0)
    for v, station in zip(path, stations, strict=True):
        got = _apply(station, centroid)
        assert got == pytest.approx(v, abs=1e-9)


def test_a_straight_path_never_twists_the_profile_between_stations():
    # A wrong implementation that recomputes an arbitrary in-plane basis
    # per station (rather than transporting the profile's own orientation)
    # can introduce spurious rotation even along a dead-straight run.
    path = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], dtype=np.float64)
    stations = sweep_stations(UNIT_SQUARE, path, closed=False)
    linear_parts = [s[:3, :3] for s in stations]
    for m in linear_parts[1:]:
        assert m == pytest.approx(linear_parts[0], abs=1e-9)


def test_a_sharp_but_survivable_corner_is_not_refused():
    # 170 degrees off straight (only 10 degrees short of a full reversal)
    # is about as sharp as a corner gets, but the profile is small (half
    # width 0.5) relative to the 10-unit segments either side of it, so
    # the miter comfortably fits. A blanket "reflex corners always refuse"
    # implementation would wrongly reject this.
    angle = np.radians(170.0)
    path = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0 + 10.0 * np.cos(angle), 10.0 * np.sin(angle), 0.0],
        ],
        dtype=np.float64,
    )
    stations = sweep_stations(UNIT_SQUARE, path, closed=False)
    assert len(stations) == 3


def test_the_same_sharp_corner_is_refused_for_a_large_enough_profile():
    # Same 170-degree turn as above, same segment lengths -- only the
    # profile grows. This is the pair the brief asks for: a criterion
    # tight at both ends must accept the small profile and reject the
    # large one on the identical corner, not just react to angle alone.
    angle = np.radians(170.0)
    path = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0 + 10.0 * np.cos(angle), 10.0 * np.sin(angle), 0.0],
        ],
        dtype=np.float64,
    )
    huge_profile = UNIT_SQUARE * 20.0
    with pytest.raises(SweepRefused):
        sweep_stations(huge_profile, path, closed=False)


def test_a_closed_path_first_and_last_station_are_both_mitered_at_the_seam():
    # Every vertex of a closed path has both a predecessor and a
    # successor, including vertex 0 (whose "incoming" segment is the
    # closing one back from the last point) -- so station 0's plane
    # normal must bisect the closing segment and the first segment, not
    # just the first and second like an open path's interior corners do.
    square_path = np.array(
        [[0, 0, 0], [4, 0, 0], [4, 4, 0], [0, 4, 0]], dtype=np.float64
    )
    stations = sweep_stations(UNIT_SQUARE, square_path, closed=True)
    seam_normal = stations[0][:3, 2]
    closing_seg = np.array([0.0, -1.0, 0.0])  # from vertex 3 back to vertex 0
    first_seg = np.array([1.0, 0.0, 0.0])  # from vertex 0 to vertex 1
    assert abs(np.dot(seam_normal, closing_seg)) == pytest.approx(
        abs(np.dot(seam_normal, first_seg)), abs=1e-9
    )
