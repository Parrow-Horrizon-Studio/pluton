"""Resolving an image file referenced by a document, safely.

Both OBJ's `map_Kd` and glTF's `image.uri` name a file relative to the
document. A document someone emailed you must not be able to name a file
outside its own directory: the bytes it points at are read into the model and
then saved, shared and exported with it, so a traversal here is a read
primitive for anything the user can open.
"""

from __future__ import annotations

from pathlib import Path


def read_sibling_image_bytes(base_dir, relative: str) -> bytes | None:
    """The bytes of `relative` resolved under `base_dir`, or None.

    Returns None rather than raising for every rejection, so a caller can stay
    best-effort. Both sides are resolved BEFORE comparison, so `..`, an
    absolute path and a symlink pointing outside are all caught; comparing the
    unresolved strings would catch only the first.
    """
    try:
        base = Path(base_dir).resolve()
        candidate = (base / relative).resolve()
        if not candidate.is_relative_to(base):
            return None
        if not candidate.is_file():
            return None
        return candidate.read_bytes()
    except (OSError, ValueError):
        return None
