"""Tests for the rule-based real-world event generator (Phase 3-B-1, task 3)."""

from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone

# Avoid the FredClient construction guard when this module imports through __init__.
os.environ.setdefault("FRED_API_KEY", "test-key-not-real")

from app.services.realworld.fred_client import FredObservation
from app.services.realworld.fred_series import FredSeries
from app.services.realworld.rule_generator import (
    RealWorldEvent,
    RuleBasedEventGenerator,
    _scale_magnitude,
)


class _StubFredClient:
    """In-memory stand-in for FredClient. Maps series_id -> observations."""

    def __init__(self, data: dict[str, list[FredObservation]]) -> None:
        self._data = data
        self.calls: list[tuple[str, int]] = []

    def get_series(self, series_id: str, observations: int = 30) -> list[FredObservation]:
        self.calls.append((series_id, observations))
        return list(self._data.get(series_id, []))


def _series(series_id: str, values: list[float | None], start: date = date(2026, 3, 1)) -> list[FredObservation]:
    """Build a synthetic observation list (oldest-first)."""
    return [
        FredObservation(series_id=series_id, date=date.fromordinal(start.toordinal() + i), value=v)
        for i, v in enumerate(values)
    ]


_FIXED_CLOCK = datetime(2026, 4, 27, 4, 0, 0, tzinfo=timezone.utc)


def _gen(client: _StubFredClient) -> RuleBasedEventGenerator:
    return RuleBasedEventGenerator(client=client, clock=lambda: _FIXED_CLOCK)


class CpiInflationRuleTests(unittest.TestCase):
    def test_cpi_up_0_5pct_emits_inflation_pressure_negative(self) -> None:
        # 0.5% MoM rise: 100.0 -> 100.5
        data = {FredSeries.CPI.value: _series(FredSeries.CPI.value, [100.0, 100.5])}
        client = _StubFredClient(data)
        event = _gen(client).generate(date(2026, 4, 27))

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_name, "Inflation Pressure")
        self.assertEqual(event.tone, "negative")
        self.assertEqual(event.event_id, "realworld-2026-04-27-inflation_pressure")
        self.assertEqual(
            event.source_urls,
            ["https://fred.stlouisfed.org/series/CPIAUCSL"],
        )
        self.assertIn("consumer", event.affected_sectors)
        self.assertIn("food", event.affected_sectors)


class OilSqueezeRuleTests(unittest.TestCase):
    def test_oil_up_8pct_emits_fuel_squeeze_with_proportional_magnitude(self) -> None:
        # 8% DoD: 80.0 -> 86.4
        data = {FredSeries.WTI_OIL.value: _series(FredSeries.WTI_OIL.value, [80.0, 86.4])}
        client = _StubFredClient(data)
        event = _gen(client).generate(date(2026, 4, 27))

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_name, "Fuel Margin Squeeze")
        self.assertEqual(event.tone, "negative")

        # 8% sits exactly at the rule's midpoint — sigmoid yields ~0.5.
        self.assertAlmostEqual(event.magnitude, 0.5, places=2)

        # A larger move should produce a larger magnitude on the same scale.
        bigger_data = {FredSeries.WTI_OIL.value: _series(FredSeries.WTI_OIL.value, [80.0, 96.0])}
        bigger_event = _gen(_StubFredClient(bigger_data)).generate(date(2026, 4, 27))
        assert bigger_event is not None
        self.assertGreater(bigger_event.magnitude, event.magnitude)

    def test_oil_down_8pct_emits_cheap_fuel_tailwind_positive(self) -> None:
        data = {FredSeries.WTI_OIL.value: _series(FredSeries.WTI_OIL.value, [80.0, 73.6])}
        client = _StubFredClient(data)
        event = _gen(client).generate(date(2026, 4, 27))

        assert event is not None
        self.assertEqual(event.event_name, "Cheap Fuel Tailwind")
        self.assertEqual(event.tone, "positive")
        self.assertIn("transportation", event.affected_sectors)


class TieBreakingTests(unittest.TestCase):
    def test_multiple_triggers_highest_abs_delta_wins(self) -> None:
        # CPI MoM +0.5% (delta=0.5) and WTI DoD +8% (delta=8).
        # WTI's |delta| is greater, so it wins.
        data = {
            FredSeries.CPI.value: _series(FredSeries.CPI.value, [100.0, 100.5]),
            FredSeries.WTI_OIL.value: _series(FredSeries.WTI_OIL.value, [80.0, 86.4]),
        }
        client = _StubFredClient(data)
        event = _gen(client).generate(date(2026, 4, 27))

        assert event is not None
        self.assertEqual(event.event_name, "Fuel Margin Squeeze")


class NoFireTests(unittest.TestCase):
    def test_flat_data_returns_none(self) -> None:
        data = {
            FredSeries.CPI.value: _series(FredSeries.CPI.value, [100.0, 100.05]),       # +0.05% MoM, below 0.3%
            FredSeries.WTI_OIL.value: _series(FredSeries.WTI_OIL.value, [80.0, 80.5]),  # +0.6% DoD, below 5%
            FredSeries.UNEMPLOYMENT.value: _series(FredSeries.UNEMPLOYMENT.value, [4.0, 4.05]),  # +0.05pp, below 0.2pp
            FredSeries.FED_FUNDS.value: _series(FredSeries.FED_FUNDS.value, [5.0, 5.10]),  # +0.10pp, below 0.25pp
        }
        client = _StubFredClient(data)
        event = _gen(client).generate(date(2026, 4, 27))
        self.assertIsNone(event)

    def test_missing_observations_handled_gracefully(self) -> None:
        # Only one observation across the board — nothing to delta against.
        data = {
            FredSeries.CPI.value: _series(FredSeries.CPI.value, [100.0]),
            FredSeries.WTI_OIL.value: _series(FredSeries.WTI_OIL.value, [80.0]),
        }
        client = _StubFredClient(data)
        self.assertIsNone(_gen(client).generate(date(2026, 4, 27)))

    def test_fred_client_failure_returns_none_not_crash(self) -> None:
        class _BoomClient:
            def get_series(self, series_id: str, observations: int = 30):
                raise RuntimeError("FRED is on fire")

        gen = RuleBasedEventGenerator(client=_BoomClient(), clock=lambda: _FIXED_CLOCK)
        self.assertIsNone(gen.generate(date(2026, 4, 27)))


class SnapshotTests(unittest.TestCase):
    """Lock down one full output object for a known input."""

    def test_locked_snapshot_for_oil_squeeze(self) -> None:
        data = {
            FredSeries.WTI_OIL.value: [
                FredObservation(series_id="DCOILWTICO", date=date(2026, 4, 25), value=80.0),
                FredObservation(series_id="DCOILWTICO", date=date(2026, 4, 26), value=86.4),
            ]
        }
        client = _StubFredClient(data)
        event = _gen(client).generate(date(2026, 4, 27))
        assert event is not None

        expected = RealWorldEvent(
            event_id="realworld-2026-04-27-fuel_margin_squeeze",
            generated_at=_FIXED_CLOCK,
            source_summary="FRED DCOILWTICO moved +8.0% DoD (2026-04-25 → 2026-04-26).",
            source_urls=["https://fred.stlouisfed.org/series/DCOILWTICO"],
            event_name="Fuel Margin Squeeze",
            narrative="Oil moved +8.0% overnight; small operators feel it first.",
            affected_sectors=["energy", "transportation", "food"],
            magnitude=0.5,
            duration_days=3,
            severity=1.3,  # midpoint of [1.0, 1.6] when magnitude == 0.5
            tone="negative",
        )
        self.assertEqual(event, expected)


class ScaleMagnitudeTests(unittest.TestCase):
    def test_at_midpoint_yields_half(self) -> None:
        self.assertAlmostEqual(_scale_magnitude(8.0, midpoint=8.0, span=4.0), 0.5, places=6)

    def test_monotonic_in_abs_delta(self) -> None:
        a = _scale_magnitude(2.0, midpoint=8.0, span=4.0)
        b = _scale_magnitude(8.0, midpoint=8.0, span=4.0)
        c = _scale_magnitude(20.0, midpoint=8.0, span=4.0)
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertLessEqual(c, 1.0)

    def test_negative_delta_uses_abs(self) -> None:
        self.assertAlmostEqual(
            _scale_magnitude(-8.0, midpoint=8.0, span=4.0),
            _scale_magnitude(8.0, midpoint=8.0, span=4.0),
            places=6,
        )

    def test_zero_span_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _scale_magnitude(1.0, midpoint=0.5, span=0.0)


if __name__ == "__main__":
    unittest.main()
