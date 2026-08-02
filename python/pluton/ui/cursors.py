"""Per-tool cursors (M7.2).

Cursors are *derived from* the icon set rather than drawn as separate art:
the tool's own glyph is composited into the lower-right of a shared base, so
redrawing an icon updates its cursor automatically and the two cannot drift.

Two bases, matching the semantics of the tools:
  CROSSHAIR - the tool places a point; the hotspot is the crosshair centre.
  ARROW     - the tool picks an existing entity, where a crosshair would
              imply an accuracy that is not being used.

The badge glyph sits on a small opaque backdrop chip so it stays legible
against the base and against whatever the cursor is hovering over -- our
icon set is thin single-stroke outlines, not filled shapes, so the glyph's
own ink cannot be relied on to read clearly (or to dominate its corner of
the cursor) on its own.

`compose_cursor` takes a `dpr` (a QScreen.devicePixelRatio()) so the cursor
stays crisp on a HiDPI display: the pixmap is rendered at `dpr` physical
pixels per logical pixel and carries that ratio as
`QPixmap.devicePixelRatio()`. Painting is done in the fixed, device-
independent CURSOR_SIZE/BADGE_SIZE coordinate space -- Qt's paint engine
scales every drawing operation against the target pixmap's devicePixelRatio,
so the same paint code produces a sharp result at any ratio. The hotspot
constants are likewise device-independent and never scaled by `dpr` in this
module: Qt re-scales them against the pixmap's own devicePixelRatio when it
binds the platform cursor, exactly as it does for the pixmap content.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap, QPolygonF

from pluton.ui.actions import CursorStyle, action_by_id
from pluton.ui.icons import icon_pixmap

CURSOR_SIZE = 32
BADGE_SIZE = 16
BADGE_ORIGIN = (CURSOR_SIZE - BADGE_SIZE, CURSOR_SIZE - BADGE_SIZE)
CROSSHAIR_HOTSPOT = (11, 11)
ARROW_HOTSPOT = (0, 0)
_CROSSHAIR_ARM = 8
_INK = QColor("#101010")
_OUTLINE = QColor("#ffffff")

# Keyed on everything that changes the rendered pixels -- style, badge stem,
# and dpr -- so two different cursors can never alias to the same cache slot.
_cursor_cache: dict[tuple[CursorStyle, str, float], QCursor] = {}


def _blank(dpr: float) -> QPixmap:
    physical = round(CURSOR_SIZE * dpr)
    pixmap = QPixmap(QSize(physical, physical))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _paint_crosshair(painter: QPainter) -> None:
    cx, cy = CROSSHAIR_HOTSPOT
    # White underlay first so the crosshair stays visible over dark geometry.
    for color, width in ((_OUTLINE, 3.0), (_INK, 1.0)):
        painter.setPen(QPen(color, width))
        painter.drawLine(cx - _CROSSHAIR_ARM, cy, cx + _CROSSHAIR_ARM, cy)
        painter.drawLine(cx, cy - _CROSSHAIR_ARM, cx, cy + _CROSSHAIR_ARM)


def _paint_badge_backdrop(painter: QPainter) -> None:
    """A light rounded chip behind the glyph.

    Same rationale as the crosshair's white halo: the badge must read clearly
    over arbitrary (often dark) viewport geometry. It also keeps the badge
    corner reliably legible regardless of how sparse a given glyph's own
    strokes are -- our icon set is thin single-stroke outlines, not filled
    shapes, so the glyph alone cannot be relied on to dominate its quadrant.
    """
    x, y = BADGE_ORIGIN
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_OUTLINE)
    painter.drawRoundedRect(QRectF(x, y, BADGE_SIZE, BADGE_SIZE), 3.0, 3.0)


def _paint_arrow(painter: QPainter) -> None:
    points = [
        (0.0, 0.0),
        (0.0, 15.0),
        (4.2, 11.2),
        (7.0, 17.0),
        (9.4, 15.8),
        (6.7, 10.2),
        (12.0, 9.8),
    ]
    polygon = QPolygonF([QPointF(x, y) for x, y in points])
    painter.setPen(QPen(_OUTLINE, 2.0))
    painter.setBrush(_INK)
    painter.drawPolygon(polygon)


def compose_cursor(style: CursorStyle, stem: str, dpr: float = 1.0) -> QCursor:
    """Paint `stem`'s glyph into the lower-right of `style`'s base pixmap.

    `dpr` selects the physical resolution the cursor is rendered at; see the
    module docstring for how the pixmap and the hotspot stay in sync.
    """
    key = (style, stem, dpr)
    cached = _cursor_cache.get(key)
    if cached is not None:
        return cached

    pixmap = _blank(dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if style is CursorStyle.CROSSHAIR:
        _paint_crosshair(painter)
        hotspot = CROSSHAIR_HOTSPOT
    else:
        _paint_arrow(painter)
        hotspot = ARROW_HOTSPOT

    _paint_badge_backdrop(painter)
    badge = icon_pixmap(stem, round(BADGE_SIZE * dpr), _INK)
    badge.setDevicePixelRatio(dpr)
    painter.drawPixmap(*BADGE_ORIGIN, badge)
    painter.end()

    built = QCursor(pixmap, hotspot[0], hotspot[1])
    _cursor_cache[key] = built
    return built


def cursor_for(action_id: str) -> QCursor:
    """The cursor for a tool action. Raises ValueError for a non-tool action."""
    spec = action_by_id(action_id)
    if spec.cursor is None or spec.icon is None:
        raise ValueError(f"{action_id} declares no cursor style")
    return compose_cursor(spec.cursor, spec.icon)


def clear_cursor_cache() -> None:
    """Drop every cached QCursor. Used by tests."""
    _cursor_cache.clear()
