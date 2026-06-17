"""Units: parse/format lengths and angles. Internal length unit is the METER.

Pure module — no Qt, no Scene. parse_* return None on unparseable input (the
caller ignores None). The model's base unit is 1 model unit = 1 meter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

INCH_M = 0.0254
_METRIC_FACTOR = {"mm": 0.001, "cm": 0.01, "m": 1.0}


class UnitSystem(Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"


@dataclass(frozen=True)
class Units:
    system: UnitSystem = UnitSystem.METRIC
    metric_unit: str = "m"          # "mm" | "cm" | "m"
    metric_precision: int = 3       # decimal places when formatting metric
    imperial_denominator: int = 16  # smallest fraction denominator (…/16")


_METRIC_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mm|cm|m)?\s*$", re.IGNORECASE)


def _parse_metric(text: str, units: Units) -> float | None:
    m = _METRIC_RE.match(text)
    if not m:
        return None
    value = float(m.group(1))
    unit = (m.group(2) or units.metric_unit).lower()
    if unit not in _METRIC_FACTOR:
        return None
    return value * _METRIC_FACTOR[unit]


def _parse_imperial(text: str) -> None:  # stub — Task 2 replaces this
    return None


def _format_imperial(meters: float, units: Units) -> str:  # stub — Task 3 replaces this
    return ""


def format_length(meters: float, units: Units) -> str:
    if units.system is UnitSystem.IMPERIAL:
        return _format_imperial(meters, units)   # Task 3
    factor = _METRIC_FACTOR.get(units.metric_unit, 1.0)
    value = meters / factor
    s = f"{value:.{units.metric_precision}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s} {units.metric_unit}"


def parse_length(text: str, units: Units) -> float | None:
    if text is None:
        return None
    t = text.strip().replace(",", ".")
    if not t:
        return None
    if "'" in t or '"' in t:
        return _parse_imperial(t)   # Task 2
    return _parse_metric(t, units)
