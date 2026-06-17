"""Units: parse/format lengths and angles. Internal length unit is the METER.

Pure module — no Qt, no Scene. parse_* return None on unparseable input (the
caller ignores None). The model's base unit is 1 model unit = 1 meter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

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


_IMPERIAL_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)?)\s*')?"           # optional feet
    r"\s*(?:(\d+)\s*)?"                        # optional whole inches
    r"(?:(\d+)\s*/\s*(\d+)\s*)?"               # optional fraction
    r'"?\s*$'                                  # optional close-quote
)


def _parse_imperial(text: str) -> float | None:
    # Require at least a foot or inch marker so plain numbers don't match here.
    if "'" not in text and '"' not in text:
        return None
    m = _IMPERIAL_RE.match(text)
    if not m:
        return None
    feet = float(m.group(1)) if m.group(1) else 0.0
    whole_in = float(m.group(2)) if m.group(2) else 0.0
    if m.group(3) and m.group(4):
        den = int(m.group(4))
        if den == 0:
            return None
        frac = int(m.group(3)) / den
    else:
        frac = 0.0
    if not (m.group(1) or m.group(2) or m.group(3)):
        return None  # empty / just a quote
    inches = feet * 12.0 + whole_in + frac
    return inches * INCH_M


def _format_imperial(meters: float, units: Units) -> str:
    den = max(1, units.imperial_denominator)
    total_in = meters / INCH_M
    # Round to the nearest 1/den inch up-front, then split.
    sixteenths = round(total_in * den)
    feet = sixteenths // (12 * den)
    rem = sixteenths - feet * 12 * den          # in 1/den inches
    whole_in = rem // den
    frac_units = rem - whole_in * den           # numerator over den
    parts: list[str] = []
    if feet:
        parts.append(f"{feet}'")
    inch_str = ""
    if whole_in or frac_units:
        if frac_units:
            f = Fraction(frac_units, den)        # reduces
            inch_str = (f"{whole_in} {f.numerator}/{f.denominator}\""
                        if whole_in else f"{f.numerator}/{f.denominator}\"")
        else:
            inch_str = f"{whole_in}\""
    if inch_str:
        parts.append(inch_str)
    if not parts:
        return "0\""
    return " ".join(parts)


_ANGLE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:°|deg|degrees)?\s*$", re.IGNORECASE)


def parse_angle(text: str) -> float | None:
    if text is None:
        return None
    m = _ANGLE_RE.match(text.strip())
    return float(m.group(1)) if m else None


def format_angle(degrees: float, precision: int = 1) -> str:
    s = f"{degrees:.{precision}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s}°"


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
        return _parse_imperial(t)
    if units.system is UnitSystem.IMPERIAL:
        # bare number → inches
        try:
            return float(t) * INCH_M if float(t) >= 0 else None
        except ValueError:
            return None
    return _parse_metric(t, units)
