"""SavedView (M7e): an immutable snapshot of a named Scene.

Holds the camera pose plus the tag-visibility and render-style state to
restore when the Scene is recalled. Pure data — no Qt. Named SavedView (not
Scene) to avoid colliding with pluton.scene.scene.Scene (the editable mesh).
"""

from __future__ import annotations

from dataclasses import dataclass

from pluton.io.document_codec import CameraState


@dataclass(frozen=True)
class SavedView:
    """One saved Scene: camera + tag visibility + render style, restored together."""

    id: int
    name: str
    camera: CameraState
    tag_visibility: dict  # dict[int, bool] — {tag_id: visible} at capture time
    face_style: str       # FaceStyle member name, e.g. "SHADED"
    xray: bool
