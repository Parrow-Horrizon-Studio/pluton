"""Execute annotation draw plans (M7d).

Deliberately thin: ALL layout lives in the pure annotations.draw_plan module.
This module only turns a plan into painter calls, so it works against any object
exposing setPen / drawLine / drawText (a QPainter in the app, a recording stub in
tests).
"""

from __future__ import annotations

from pluton.annotations.draw_plan import CHAR_W_PX


def _align_offset(text: str, align: str) -> float:
    if align == "center":
        return -0.5 * CHAR_W_PX * max(len(text), 1)
    if align == "right":
        return -CHAR_W_PX * max(len(text), 1)
    return 0.0


def paint_annotation_plans(painter, plans, color, selected_ids, selected_color) -> None:
    """Draw every plan; annotations whose id is in `selected_ids` use the
    selection colour."""
    for plan in plans:
        is_selected = plan.annotation_id in selected_ids
        painter.setPen(selected_color if is_selected else color)
        for x1, y1, x2, y2 in plan.segments_px:
            painter.drawLine(x1, y1, x2, y2)
        for text in plan.texts:
            painter.drawText(text.x + _align_offset(text.text, text.align), text.y, text.text)
