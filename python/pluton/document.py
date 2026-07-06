"""DocumentSettings — per-document preferences (in-memory for M4d).

Holds the active Units. File persistence arrives with the native format (M6).
"""

from __future__ import annotations

from pluton.units import Units, UnitSystem


class DocumentSettings:
    def __init__(self) -> None:
        self._units = Units()

    @property
    def units(self) -> Units:
        return self._units

    def set_metric(self, metric_unit: str = "m") -> None:
        self._units = Units(
            system=UnitSystem.METRIC,
            metric_unit=metric_unit,
            metric_precision=self._units.metric_precision,
            imperial_denominator=self._units.imperial_denominator,
        )

    def set_imperial(self, denominator: int = 16) -> None:
        self._units = Units(
            system=UnitSystem.IMPERIAL,
            imperial_denominator=denominator,
            metric_unit=self._units.metric_unit,
            metric_precision=self._units.metric_precision,
        )

    def set_units(self, units: Units) -> None:
        """Replace the active units wholesale (used by file load / New)."""
        self._units = units
