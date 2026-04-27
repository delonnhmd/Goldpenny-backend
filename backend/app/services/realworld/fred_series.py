"""Whitelist of FRED series the real-world pipeline knows how to read.

Adding a series here does not automatically wire it into the rule generator —
the rules in ``rule_generator.py`` reference these constants explicitly.
"""

from __future__ import annotations

from enum import Enum


class FredSeries(str, Enum):
    """FRED series IDs supported by the Phase 3-B-1 pipeline."""

    CPI = "CPIAUCSL"          # Consumer Price Index (monthly)
    UNEMPLOYMENT = "UNRATE"   # Unemployment rate (monthly)
    WTI_OIL = "DCOILWTICO"    # WTI crude oil spot price (daily)
    FED_FUNDS = "DFF"         # Effective federal funds rate (daily)
    INDUSTRIAL = "INDPRO"     # Industrial production index (monthly)


SUPPORTED_SERIES_IDS: frozenset[str] = frozenset(s.value for s in FredSeries)
