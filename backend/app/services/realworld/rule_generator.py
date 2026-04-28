"""Rule-based real-world event generator (Phase 3-B-1, task 3).

Pulls FRED observations via FredClient, computes deltas, and emits at most
one ``RealWorldEvent`` per game day. No AI / LLM — narrative text is
template-based f-string formatting tuned per rule.

Rules currently encoded:

- CPIAUCSL MoM > +0.3%   →  Inflation Pressure          (negative)
- DCOILWTICO DoD > +5%   →  Fuel Margin Squeeze         (negative)
- DCOILWTICO DoD < -5%   →  Cheap Fuel Tailwind         (positive)
- UNRATE MoM > +0.2pp    →  Job Market Weakness         (negative)
- DFF up > +0.25pp       →  Rate Hike                   (negative)

When multiple rules fire on the same day, the rule with the highest
computed magnitude wins. Magnitude is normalized 0.0-1.0 per rule via
``_scale_magnitude``, making it the only valid comparison across
heterogeneous indicators (CPI, oil, unemployment, rates) which have
different units, scales, and typical volatility ranges.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Literal

from app.services.realworld.fred_client import FredClient, FredObservation
from app.services.realworld.fred_series import FredSeries

logger = logging.getLogger(__name__)


Tone = Literal["positive", "neutral", "negative"]


# Every rule must register its category here. New rules without a mapping fail loudly, on purpose.
# Values must match strings already used by the static catalog in
# backend/app/engine/event_catalog.py (consumer, energy, financial, labor, etc.).
RULE_TO_CATEGORY: dict[str, str] = {
    "inflation_pressure": "consumer",
    "fuel_margin_squeeze": "energy",
    "cheap_fuel_tailwind": "energy",
    "job_market_weakness": "labor",
    "rate_hike": "financial",
}


@dataclass(frozen=True)
class RealWorldEvent:
    """Generator output. Mirrors the schema locked in CORE_LOOP.md."""

    event_id: str
    generated_at: datetime
    source_summary: str
    source_urls: list[str]
    event_name: str
    narrative: str
    affected_sectors: list[str]
    magnitude: float
    duration_days: int
    severity: float
    tone: Tone


# ---------------------------------------------------------------------------
# Magnitude scaling — shared across rules for comparability.
# ---------------------------------------------------------------------------


def _scale_magnitude(delta: float, midpoint: float, span: float) -> float:
    """Map ``abs(delta)`` onto [0.0, 1.0] via a sigmoid centred at ``midpoint``.

    At ``|delta| == midpoint`` returns ~0.5; large deltas saturate towards 1.
    A larger ``span`` flattens the curve (more headroom before saturation).

    The sigmoid is preferred over hard clipping because it keeps the output
    monotonic and bounded, so comparing magnitudes across rules with very
    different threshold scales (e.g. 0.3% CPI vs 5% oil) stays meaningful.
    """
    if span <= 0:
        raise ValueError("span must be > 0")
    z = (abs(delta) - midpoint) / span
    return 1.0 / (1.0 + math.exp(-z))


def _severity_from_magnitude(magnitude: float, lo: float, hi: float) -> float:
    """Linearly map magnitude in [0,1] to severity in [lo, hi]."""
    return round(lo + (hi - lo) * magnitude, 4)


# ---------------------------------------------------------------------------
# Delta helpers.
# ---------------------------------------------------------------------------


def _last_two_non_null(observations: list[FredObservation]) -> tuple[FredObservation, FredObservation] | None:
    """Return ``(previous, latest)`` pair of non-null observations, or None."""
    non_null = [o for o in observations if o.value is not None]
    if len(non_null) < 2:
        return None
    return non_null[-2], non_null[-1]


def _pct_change(prev: float, latest: float) -> float | None:
    """Return percent change as a number (0.5 means +0.5%). None if undefined."""
    if prev == 0:
        return None
    return (latest - prev) / prev * 100.0


def _pp_change(prev: float, latest: float) -> float:
    """Return change in percentage points (already-rate series like UNRATE/DFF)."""
    return latest - prev


# ---------------------------------------------------------------------------
# Rule definitions.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Trigger:
    """One firing rule. Internal — never exposed."""

    rule_slug: str
    series_id: str
    delta: float                 # signed, in the rule's native unit
    event_name: str
    tone: Tone
    affected_sectors: tuple[str, ...]
    magnitude: float
    severity: float
    duration_days: int
    narrative: str
    source_summary: str


def _maybe_cpi(obs: list[FredObservation]) -> _Trigger | None:
    pair = _last_two_non_null(obs)
    if not pair:
        return None
    prev, latest = pair
    pct = _pct_change(prev.value, latest.value)
    if pct is None or pct <= 0.3:
        return None
    magnitude = _scale_magnitude(pct, midpoint=0.5, span=0.3)
    return _Trigger(
        rule_slug="inflation_pressure",
        series_id=FredSeries.CPI.value,
        delta=pct,
        event_name="Inflation Pressure",
        tone="negative",
        affected_sectors=("consumer", "food", "transportation"),
        magnitude=magnitude,
        severity=_severity_from_magnitude(magnitude, 1.2, 1.8),
        duration_days=5,
        narrative=(
            f"Consumer prices climbed {pct:+.2f}% month-over-month. "
            f"Households feel it at the grocery store and the gas pump."
        ),
        source_summary=(
            f"FRED CPIAUCSL rose {pct:+.2f}% MoM "
            f"({prev.date.isoformat()} → {latest.date.isoformat()})."
        ),
    )


def _maybe_oil(obs: list[FredObservation]) -> _Trigger | None:
    pair = _last_two_non_null(obs)
    if not pair:
        return None
    prev, latest = pair
    pct = _pct_change(prev.value, latest.value)
    if pct is None:
        return None
    if pct > 5.0:
        magnitude = _scale_magnitude(pct, midpoint=8.0, span=4.0)
        return _Trigger(
            rule_slug="fuel_margin_squeeze",
            series_id=FredSeries.WTI_OIL.value,
            delta=pct,
            event_name="Fuel Margin Squeeze",
            tone="negative",
            affected_sectors=("energy", "transportation", "food"),
            magnitude=magnitude,
            severity=_severity_from_magnitude(magnitude, 1.0, 1.6),
            duration_days=3,
            narrative=(
                f"Oil moved {pct:+.1f}% overnight; small operators feel it first."
            ),
            source_summary=(
                f"FRED DCOILWTICO moved {pct:+.1f}% DoD "
                f"({prev.date.isoformat()} → {latest.date.isoformat()})."
            ),
        )
    if pct < -5.0:
        magnitude = _scale_magnitude(pct, midpoint=8.0, span=4.0)
        return _Trigger(
            rule_slug="cheap_fuel_tailwind",
            series_id=FredSeries.WTI_OIL.value,
            delta=pct,
            event_name="Cheap Fuel Tailwind",
            tone="positive",
            affected_sectors=("transportation", "consumer"),
            magnitude=magnitude,
            severity=_severity_from_magnitude(magnitude, 0.8, 1.2),
            duration_days=3,
            narrative=(
                f"Oil dropped {pct:+.1f}% overnight; rideshare and trucking margins ease."
            ),
            source_summary=(
                f"FRED DCOILWTICO moved {pct:+.1f}% DoD "
                f"({prev.date.isoformat()} → {latest.date.isoformat()})."
            ),
        )
    return None


def _maybe_unemployment(obs: list[FredObservation]) -> _Trigger | None:
    pair = _last_two_non_null(obs)
    if not pair:
        return None
    prev, latest = pair
    pp = _pp_change(prev.value, latest.value)
    if pp <= 0.2:
        return None
    magnitude = _scale_magnitude(pp, midpoint=0.4, span=0.2)
    return _Trigger(
        rule_slug="job_market_weakness",
        series_id=FredSeries.UNEMPLOYMENT.value,
        delta=pp,
        event_name="Job Market Weakness",
        tone="negative",
        affected_sectors=("services", "consumer"),
        magnitude=magnitude,
        severity=_severity_from_magnitude(magnitude, 1.2, 1.6),
        duration_days=7,
        narrative=(
            f"Unemployment rose {pp:+.2f} percentage points. "
            f"Service-sector hiring stalls and discretionary spending tightens."
        ),
        source_summary=(
            f"FRED UNRATE rose {pp:+.2f}pp MoM "
            f"({prev.date.isoformat()} → {latest.date.isoformat()})."
        ),
    )


def _maybe_fed_funds(obs: list[FredObservation]) -> _Trigger | None:
    pair = _last_two_non_null(obs)
    if not pair:
        return None
    prev, latest = pair
    pp = _pp_change(prev.value, latest.value)
    if pp <= 0.25:
        return None
    magnitude = _scale_magnitude(pp, midpoint=0.5, span=0.25)
    return _Trigger(
        rule_slug="rate_hike",
        series_id=FredSeries.FED_FUNDS.value,
        delta=pp,
        event_name="Rate Hike",
        tone="negative",
        affected_sectors=("finance", "real_estate", "consumer"),
        magnitude=magnitude,
        severity=_severity_from_magnitude(magnitude, 1.4, 1.8),
        duration_days=10,
        narrative=(
            f"Fed funds jumped {pp:+.2f} percentage points. "
            f"Mortgages, credit cards, and small-business loans all get pricier overnight."
        ),
        source_summary=(
            f"FRED DFF rose {pp:+.2f}pp since the previous reading "
            f"({prev.date.isoformat()} → {latest.date.isoformat()})."
        ),
    )


# Mapping series → rule evaluators that depend on that series.
_RULE_EVALUATORS: tuple[tuple[str, Callable[[list[FredObservation]], "_Trigger | None"]], ...] = (
    (FredSeries.CPI.value, _maybe_cpi),
    (FredSeries.WTI_OIL.value, _maybe_oil),
    (FredSeries.UNEMPLOYMENT.value, _maybe_unemployment),
    (FredSeries.FED_FUNDS.value, _maybe_fed_funds),
)


# ---------------------------------------------------------------------------
# Public generator.
# ---------------------------------------------------------------------------


class RuleBasedEventGenerator:
    """Deterministic FRED-driven event generator.

    Stateless; safe to construct per-call. Inject a ``FredClient`` for tests.
    """

    def __init__(
        self,
        client: FredClient | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client if client is not None else FredClient()
        self._clock = clock if clock is not None else (lambda: datetime.now(timezone.utc))

    def generate(self, today: date) -> RealWorldEvent | None:
        """Return today's event or None if no rule fires.

        Surprising FRED data (missing observations, wrong shapes) is logged
        and treated as a no-fire — never a crash. The cron job's fallback
        chain handles the None.
        """
        triggers: list[_Trigger] = []
        for series_id, evaluator in _RULE_EVALUATORS:
            try:
                obs = self._client.get_series(series_id, observations=30)
            except Exception as exc:  # noqa: BLE001 — defensive: any FRED failure → skip
                logger.warning("rule_generator: FRED fetch failed series_id=%s err=%s", series_id, exc)
                continue
            try:
                trig = evaluator(obs)
            except Exception as exc:  # noqa: BLE001 — surprising data → skip
                logger.warning("rule_generator: evaluator raised series_id=%s err=%s", series_id, exc)
                continue
            if trig is not None:
                triggers.append(trig)

        if not triggers:
            return None

        # Highest computed magnitude wins — magnitude is normalized 0.0–1.0 per
        # rule, so it's the only meaningful cross-indicator comparison. Ties
        # broken by rule_slug (stable, deterministic).
        winner = max(triggers, key=lambda t: (t.magnitude, t.rule_slug))
        return RealWorldEvent(
            event_id=f"realworld-{today.isoformat()}-{winner.rule_slug}",
            generated_at=self._clock(),
            source_summary=winner.source_summary,
            source_urls=[f"https://fred.stlouisfed.org/series/{winner.series_id}"],
            event_name=winner.event_name,
            narrative=winner.narrative,
            affected_sectors=list(winner.affected_sectors),
            magnitude=round(winner.magnitude, 4),
            duration_days=winner.duration_days,
            severity=winner.severity,
            tone=winner.tone,
        )
