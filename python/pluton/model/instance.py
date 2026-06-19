from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pluton.model.definition import Definition


class Instance:
    """A placement: a 4x4 transform + a reference to a Definition. Non-destructive."""

    __slots__ = ("id", "definition", "transform")

    def __init__(
        self, instance_id: int, definition: "Definition", transform: np.ndarray | None = None
    ) -> None:
        self.id = int(instance_id)
        self.definition = definition
        if transform is None:
            self.transform = np.eye(4, dtype=np.float64)
        else:
            self.transform = np.asarray(transform, dtype=np.float64).reshape(4, 4).copy()
