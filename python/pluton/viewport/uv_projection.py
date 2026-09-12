"""Project face corners onto their own plane to get texture coordinates.

Faces store no UVs (spec D1). A material carries a real-world `texture_size`,
and each face's corners are projected onto a basis built on that face's plane,
divided by that size, then optionally adjusted by a per-face placement.

Pure numpy. No model, no scene, no Qt, no GL, so every function here is
testable with no QApplication and no GL context.
"""

from __future__ import annotations

import numpy as np

# A normal this close to a world axis makes that axis a poor choice of seed for
# the cross product, because the result approaches zero length.
_AXIS_ALIGNED = 0.9


def plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """An orthonormal (u, v) pair spanning the plane perpendicular to `normal`.

    Derived from the normal alone, deliberately. A basis taken from the face's
    first edge would change whenever an unrelated edit changed which vertex the
    loop starts at, spinning the texture on a face nobody touched.
    """
    n = np.asarray(normal, dtype=np.float64).reshape(3)
    length = float(np.linalg.norm(n))
    if length == 0.0:
        return (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
        )
    nx, ny, nz = (float(c) / length for c in n)
    # cross(seed, n) and cross(n, u) written out as scalar arithmetic. The seed
    # is always a unit world axis, so the first cross collapses to two negations
    # and the second is three multiply-subtracts — the same floating-point
    # operations np.cross performs, without its moveaxis/broadcast dispatch.
    # That dispatch dominated the profile: building the UVs for a 9,600-face
    # definition spent 0.72 s of 1.14 s in np.cross on 3-vectors.
    if abs(nz) < _AXIS_ALIGNED:
        ux, uy, uz = -ny, nx, 0.0  # cross((0, 0, 1), n)
    else:
        ux, uy, uz = 0.0, -nz, ny  # cross((1, 0, 0), n)
    u_len = (ux * ux + uy * uy + uz * uz) ** 0.5
    ux, uy, uz = ux / u_len, uy / u_len, uz / u_len
    return (
        np.array([ux, uy, uz]),
        np.array([ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux]),
    )


def project_corners(
    positions: np.ndarray,
    normal: np.ndarray,
    origin: np.ndarray,
    texture_size: tuple[float, float],
) -> np.ndarray:
    """(N, 3) corners of one face to (N, 2) UVs, in texture tiles.

    `texture_size` is the image's extent in MODEL UNITS, so a 1x1 texture on a
    2x2 face spans two tiles rather than being stretched to fit.
    """
    pts = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    if pts.shape[0] == 0:
        return np.zeros((0, 2), dtype=np.float32)
    u_axis, v_axis = plane_basis(normal)
    rel = pts - np.asarray(origin, dtype=np.float64).reshape(3)
    su = float(texture_size[0]) or 1.0
    sv = float(texture_size[1]) or 1.0
    uvs = np.stack([rel @ u_axis / su, rel @ v_axis / sv], axis=1)
    return uvs.astype(np.float32)


def apply_placement(
    uvs: np.ndarray,
    offset_u: float,
    offset_v: float,
    scale: float,
    rotation: float,
) -> np.ndarray:
    """Scale, then rotate, then offset. That order is contractual.

    A larger `scale` makes the image cover more surface, so the UV is DIVIDED
    by it. Task 10's numeric fields and Task 12's drag both depend on this
    order matching, and a different one passes any test that varies a single
    parameter at a time.
    """
    out = np.asarray(uvs, dtype=np.float64).reshape(-1, 2)
    if out.shape[0] == 0:
        return np.zeros((0, 2), dtype=np.float32)
    s = float(scale) or 1.0
    out = out / s
    if rotation:
        c, sn = np.cos(float(rotation)), np.sin(float(rotation))
        rot = np.array([[c, -sn], [sn, c]])
        out = out @ rot.T
    out = out + np.array([float(offset_u), float(offset_v)])
    return out.astype(np.float32)
