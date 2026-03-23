"""Economy Engine — Step 5.

The central macro-simulation brain for Gold Penny.

Design rules
------------
- This engine NEVER directly modifies player cash or balances.
- It only shifts *pressure factors* that other engines read.
- All variable changes are clamped and event-capped to keep gameplay sane.
"""

from __future__ import annotations

import json
import random
from typing import Any

from sqlalchemy.orm import Session

from app.models.economy import EconomyState
from app.models.economy_event import EconomyEvent
from app.models.economy_history import EconomyHistory
from app.models.game_state import GameState
from app.models.sector_index import SectorIndex

# ── Constants ─────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, float] = {
    "inflation_rate": 2.5,
    "interest_rate": 4.5,
    "unemployment_rate": 5.0,
    "oil_index": 100.0,
    "consumer_confidence": 100.0,
    "supply_chain_index": 100.0,
    "seasonal_index": 100.0,
}

# Maximum random drift applied each day even without an event.
_DRIFT_CAPS: dict[str, float] = {
    "inflation_rate": 0.10,
    "interest_rate": 0.05,
    "unemployment_rate": 0.08,
    "oil_index": 2.0,
    "consumer_confidence": 1.5,
    "supply_chain_index": 1.5,
    "seasonal_index": 1.0,
}

# Maximum total impact any single event may apply per day.
_EVENT_CAPS: dict[str, float] = {
    "inflation_rate": 0.30,
    "interest_rate": 0.15,
    "unemployment_rate": 0.50,
    "oil_index": 6.0,
    "consumer_confidence": 5.0,
    "supply_chain_index": 6.0,
    "seasonal_index": 4.0,
}

# Hard gameplay bounds for every macro variable.
_CLAMPS: dict[str, tuple[float, float]] = {
    "inflation_rate": (0.0, 15.0),
    "interest_rate": (0.0, 20.0),
    "unemployment_rate": (1.0, 25.0),
    "oil_index": (50.0, 200.0),
    "consumer_confidence": (50.0, 150.0),
    "supply_chain_index": (50.0, 150.0),
    "seasonal_index": (80.0, 120.0),
}

_SECTORS: list[str] = [
    "energy", "tech", "retail", "health", "bank",
    "auto", "transport", "real_estate", "defense", "consumer",
]

_SECTOR_DRIVERS: dict[str, str] = {
    "energy": "oil_index, supply_chain_index",
    "tech": "interest_rate, consumer_confidence",
    "retail": "inflation_rate, consumer_confidence",
    "health": "inflation_rate",
    "bank": "interest_rate, unemployment_rate",
    "auto": "consumer_confidence, interest_rate",
    "transport": "oil_index, supply_chain_index",
    "real_estate": "interest_rate",
    "defense": "unemployment_rate",
    "consumer": "consumer_confidence, inflation_rate",
}

# Pool of system-generated fallback events.
_FALLBACK_EVENTS: list[dict[str, Any]] = [
    {
        "title": "Port delays raise import costs",
        "description": "Shipping bottlenecks at major ports slow goods delivery and lift import prices.",
        "event_type": "supply_chain",
        "inflation_impact": 0.08,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.05,
        "oil_impact": 1.2,
        "confidence_impact": -1.0,
        "supply_chain_impact": -2.5,
        "seasonal_impact": 0.0,
        "severity": "minor",
    },
    {
        "title": "Hiring slowdown hits consumer outlook",
        "description": "Employers pull back on new positions, dampening household spending expectations.",
        "event_type": "labor",
        "inflation_impact": -0.05,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.12,
        "oil_impact": 0.0,
        "confidence_impact": -2.5,
        "supply_chain_impact": 0.0,
        "seasonal_impact": 0.0,
        "severity": "minor",
    },
    {
        "title": "Fuel supply disruption lifts transport costs",
        "description": "Regional fuel supply issues push transport and delivery costs higher.",
        "event_type": "energy",
        "inflation_impact": 0.12,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.0,
        "oil_impact": 3.5,
        "confidence_impact": -1.5,
        "supply_chain_impact": -1.5,
        "seasonal_impact": 0.0,
        "severity": "moderate",
    },
    {
        "title": "Stable employment supports household confidence",
        "description": "Low job losses and steady payrolls lift spending confidence.",
        "event_type": "labor",
        "inflation_impact": 0.03,
        "interest_rate_impact": 0.0,
        "unemployment_impact": -0.08,
        "oil_impact": 0.0,
        "confidence_impact": 2.0,
        "supply_chain_impact": 0.0,
        "seasonal_impact": 0.0,
        "severity": "minor",
    },
    {
        "title": "Strong harvest eases produce pressure",
        "description": "Favorable growing conditions bring agricultural prices down.",
        "event_type": "agriculture",
        "inflation_impact": -0.06,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.0,
        "oil_impact": 0.0,
        "confidence_impact": 1.0,
        "supply_chain_impact": 1.5,
        "seasonal_impact": 3.0,
        "severity": "minor",
    },
    {
        "title": "Consumer spending holds steady",
        "description": "Retail activity remains stable across major spending categories.",
        "event_type": "retail",
        "inflation_impact": 0.04,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.0,
        "oil_impact": 0.0,
        "confidence_impact": 1.0,
        "supply_chain_impact": 0.5,
        "seasonal_impact": 0.0,
        "severity": "minor",
    },
    {
        "title": "Central bank holds interest rates steady",
        "description": "Policymakers keep rates unchanged amid mixed economic signals.",
        "event_type": "finance",
        "inflation_impact": 0.0,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.0,
        "oil_impact": 0.0,
        "confidence_impact": 0.5,
        "supply_chain_impact": 0.0,
        "seasonal_impact": 0.0,
        "severity": "minor",
    },
    {
        "title": "Transport network disruption hits delivery times",
        "description": "Road and rail delays add costs across the supply chain.",
        "event_type": "transportation",
        "inflation_impact": 0.07,
        "interest_rate_impact": 0.0,
        "unemployment_impact": 0.04,
        "oil_impact": 1.5,
        "confidence_impact": -1.0,
        "supply_chain_impact": -3.0,
        "seasonal_impact": 0.0,
        "severity": "moderate",
    },
    {
        "title": "Interest rate hike dampens borrowing activity",
        "description": "Central bank raises rates slightly to combat persistent inflation.",
        "event_type": "finance",
        "inflation_impact": -0.05,
        "interest_rate_impact": 0.10,
        "unemployment_impact": 0.04,
        "oil_impact": 0.0,
        "confidence_impact": -1.5,
        "supply_chain_impact": 0.0,
        "seasonal_impact": 0.0,
        "severity": "moderate",
    },
    {
        "title": "Defense sector buoys economic stability",
        "description": "Government procurement lifts employment in manufacturing and logistics.",
        "event_type": "neutral",
        "inflation_impact": 0.02,
        "interest_rate_impact": 0.0,
        "unemployment_impact": -0.05,
        "oil_impact": 0.5,
        "confidence_impact": 0.8,
        "supply_chain_impact": 0.0,
        "seasonal_impact": 0.0,
        "severity": "minor",
    },
]

# ── Pure helper functions ──────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _cap(delta: float, cap: float) -> float:
    """Clamp a delta to ±cap."""
    return max(-cap, min(cap, delta))


# ── Engine ────────────────────────────────────────────────────────────────────

class EconomyEngine:
    """Daily macro-economy simulation engine for Gold Penny."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    # ── Public API ────────────────────────────────────────────────────────────

    def process_next_day_economy(self, day: int, db: Session) -> dict[str, Any]:
        """Process and persist economy state for *day*.

        Idempotent — calling this twice for the same day returns the existing
        result without modifying anything.
        """
        existing = db.query(EconomyState).filter(EconomyState.day == day).first()
        if existing is not None:
            return self._build_summary(existing)

        prev = self._load_previous_state(day, db)
        events = self._load_events_for_day(day, db)
        if not events:
            event = self._generate_fallback_event(day, db)
            events = [event]

        # Start from previous values.
        values: dict[str, float] = {
            "inflation_rate": prev.inflation_rate,
            "interest_rate": prev.interest_rate,
            "unemployment_rate": prev.unemployment_rate,
            "oil_index": prev.oil_index,
            "consumer_confidence": prev.consumer_confidence,
            "supply_chain_index": prev.supply_chain_index,
            "seasonal_index": prev.seasonal_index,
        }

        # Apply capped event impacts.
        for event in events:
            values["inflation_rate"] += _cap(event.inflation_impact, _EVENT_CAPS["inflation_rate"])
            values["interest_rate"] += _cap(event.interest_rate_impact, _EVENT_CAPS["interest_rate"])
            values["unemployment_rate"] += _cap(event.unemployment_impact, _EVENT_CAPS["unemployment_rate"])
            values["oil_index"] += _cap(event.oil_impact, _EVENT_CAPS["oil_index"])
            values["consumer_confidence"] += _cap(event.confidence_impact, _EVENT_CAPS["consumer_confidence"])
            values["supply_chain_index"] += _cap(event.supply_chain_impact, _EVENT_CAPS["supply_chain_index"])
            values["seasonal_index"] += _cap(event.seasonal_impact, _EVENT_CAPS["seasonal_index"])

        # Apply bounded random drift (world never completely freezes).
        for key, cap in _DRIFT_CAPS.items():
            values[key] += self.rng.uniform(-cap, cap)

        # Hard-clamp all variables.
        for key, (lo, hi) in _CLAMPS.items():
            values[key] = round(_clamp(values[key], lo, hi), 4)

        pressures = self._calculate_pressures(values)
        sector_data = self._generate_sector_indices(values, day, db)
        sector_summary = json.dumps(
            {s["sector_name"]: round(s["daily_change_percent"], 3) for s in sector_data}
        )

        # Persist new economy state.
        state = EconomyState(
            day=day,
            inflation_rate=values["inflation_rate"],
            interest_rate=values["interest_rate"],
            unemployment_rate=values["unemployment_rate"],
            oil_index=values["oil_index"],
            consumer_confidence=values["consumer_confidence"],
            supply_chain_index=values["supply_chain_index"],
            seasonal_index=values["seasonal_index"],
            event_count=len(events),
            notes=None,
        )
        db.add(state)

        # Persist history snapshot.
        history = EconomyHistory(
            day=day,
            inflation_rate=values["inflation_rate"],
            interest_rate=values["interest_rate"],
            unemployment_rate=values["unemployment_rate"],
            oil_index=values["oil_index"],
            consumer_confidence=values["consumer_confidence"],
            supply_chain_index=values["supply_chain_index"],
            seasonal_index=values["seasonal_index"],
            basket_price_pressure=pressures["basket_price_pressure"],
            layoff_pressure=pressures["layoff_pressure"],
            wage_pressure=pressures["wage_pressure"],
            sector_pressure_summary=sector_summary,
        )
        db.add(history)
        db.commit()
        db.refresh(state)

        self._mark_economy_processed(day, db)
        return self._build_summary(state, pressures=pressures)

    def get_current_state(self, db: Session) -> dict[str, Any] | None:
        """Return a summary dict for the latest economy state, or None."""
        state = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
        if state is None:
            return None
        return self._build_summary(state)

    def get_price_factors(self, db: Session) -> dict[str, float]:
        """Return factor multipliers for use by the basket / shop engine."""
        state = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
        if state is None:
            return {
                "inflation_factor": 1.0,
                "oil_factor": 1.0,
                "supply_chain_factor": 1.0,
                "seasonal_factor": 1.0,
            }
        return {
            "inflation_factor": round(1.0 + ((state.inflation_rate - 2.5) * 0.01), 4),
            "oil_factor": round(state.oil_index / 100.0, 4),
            "supply_chain_factor": round(state.supply_chain_index / 100.0, 4),
            "seasonal_factor": round(state.seasonal_index / 100.0, 4),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_previous_state(self, day: int, db: Session) -> EconomyState:
        prev = (
            db.query(EconomyState)
            .filter(EconomyState.day < day)
            .order_by(EconomyState.day.desc())
            .first()
        )
        if prev is not None:
            return prev
        # Bootstrap: return an in-memory object with day-1 defaults (not persisted).
        return EconomyState(
            day=day - 1,
            **{k: v for k, v in _DEFAULTS.items()},
        )

    def _load_events_for_day(self, day: int, db: Session) -> list[EconomyEvent]:
        return db.query(EconomyEvent).filter(EconomyEvent.day == day).all()

    def _generate_fallback_event(self, day: int, db: Session) -> EconomyEvent:
        """Create and persist one system-generated event for *day*.

        Guards against duplicates — returns existing if one already exists.
        """
        existing = (
            db.query(EconomyEvent)
            .filter(EconomyEvent.day == day, EconomyEvent.is_system_generated.is_(True))
            .first()
        )
        if existing is not None:
            return existing

        template = self.rng.choice(_FALLBACK_EVENTS)
        event = EconomyEvent(
            day=day,
            title=template["title"],
            description=template["description"],
            event_type=template["event_type"],
            inflation_impact=template["inflation_impact"],
            interest_rate_impact=template["interest_rate_impact"],
            unemployment_impact=template["unemployment_impact"],
            oil_impact=template["oil_impact"],
            confidence_impact=template["confidence_impact"],
            supply_chain_impact=template["supply_chain_impact"],
            seasonal_impact=template["seasonal_impact"],
            severity=template["severity"],
            is_system_generated=True,
        )
        db.add(event)
        db.flush()  # get id without committing the outer transaction
        return event

    def _calculate_pressures(self, values: dict[str, float]) -> dict[str, float]:
        """Derive downstream pressure multipliers from current macro values."""
        inflation = values["inflation_rate"]
        oil = values["oil_index"]
        supply = values["supply_chain_index"]
        unemployment = values["unemployment_rate"]
        confidence = values["consumer_confidence"]

        basket = (
            1.0
            + ((inflation - 2.5) * 0.03)
            + ((oil - 100.0) * 0.002)
            + ((supply - 100.0) * 0.003)
        )
        basket = round(_clamp(basket, 0.80, 1.40), 4)

        layoff = (
            1.0
            + ((unemployment - 5.0) * 0.05)
            - ((confidence - 100.0) * 0.003)
            + ((supply - 100.0) * 0.002)
        )
        layoff = round(_clamp(layoff, 0.70, 1.60), 4)

        wage = (
            1.0
            + ((inflation - 2.5) * 0.02)
            - ((unemployment - 5.0) * 0.02)
            + ((confidence - 100.0) * 0.002)
        )
        wage = round(_clamp(wage, 0.80, 1.30), 4)

        return {
            "basket_price_pressure": basket,
            "layoff_pressure": layoff,
            "wage_pressure": wage,
        }

    def _generate_sector_indices(
        self, values: dict[str, float], day: int, db: Session
    ) -> list[dict[str, Any]]:
        """Calculate and persist daily sector performance for each sector.

        Skips sectors that already have a row for *day* (idempotent).
        """
        inflation = values["inflation_rate"]
        interest = values["interest_rate"]
        unemployment = values["unemployment_rate"]
        oil = values["oil_index"]
        confidence = values["consumer_confidence"]
        supply = values["supply_chain_index"]

        # Per-sector macro effect formula (in percentage points).
        sector_effects: dict[str, float] = {
            "energy": (oil - 100.0) * 0.04 + (supply - 100.0) * 0.01,
            "tech": -((interest - 4.5) * 0.05) + (confidence - 100.0) * 0.02,
            "retail": -((inflation - 2.5) * 0.03) + (confidence - 100.0) * 0.03,
            "health": -(abs(inflation - 2.5) * 0.01),  # defensive — low volatility
            "bank": (interest - 4.5) * 0.04 - (unemployment - 5.0) * 0.02,
            "auto": (confidence - 100.0) * 0.03 - (interest - 4.5) * 0.04,
            "transport": -((oil - 100.0) * 0.03) - ((supply - 100.0) * 0.02),
            "real_estate": -((interest - 4.5) * 0.08),
            "defense": 0.02 + (unemployment - 5.0) * 0.005,
            "consumer": (confidence - 100.0) * 0.025 - (inflation - 2.5) * 0.02,
        }

        # Sectors already recorded for this day (duplicate guard).
        existing: set[str] = {
            row.sector_name
            for row in db.query(SectorIndex.sector_name)
            .filter(SectorIndex.day == day)
            .all()
        }

        # Previous sector index values for compounding.
        prev_values: dict[str, float] = {}
        for sector in _SECTORS:
            prev_row = (
                db.query(SectorIndex)
                .filter(SectorIndex.sector_name == sector, SectorIndex.day < day)
                .order_by(SectorIndex.day.desc())
                .first()
            )
            prev_values[sector] = prev_row.sector_index_value if prev_row else 100.0

        results: list[dict[str, Any]] = []
        for sector in _SECTORS:
            macro_effect = sector_effects[sector]
            noise = self.rng.uniform(-1.0, 1.0)
            daily_change = round(macro_effect + noise, 4)
            prev_val = prev_values[sector]
            new_val = round(_clamp(prev_val * (1 + daily_change / 100.0), 10.0, 500.0), 4)

            results.append(
                {
                    "sector_name": sector,
                    "sector_index_value": new_val,
                    "daily_change_percent": daily_change,
                    "macro_driver": _SECTOR_DRIVERS[sector],
                }
            )

            if sector not in existing:
                db.add(
                    SectorIndex(
                        day=day,
                        sector_name=sector,
                        sector_index_value=new_val,
                        daily_change_percent=daily_change,
                        macro_driver=_SECTOR_DRIVERS[sector],
                    )
                )

        return results

    def _mark_economy_processed(self, day: int, db: Session) -> None:
        """Record which day was last economy-processed on the GameState row."""
        try:
            state = db.query(GameState).order_by(GameState.id.asc()).first()
            if state is None:
                return
            state.economy_processed_for_day = day
            db.commit()
        except Exception:
            # Column may not exist yet on older DB schemas — non-fatal.
            db.rollback()

    def _build_summary(
        self,
        state: EconomyState,
        pressures: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        if pressures is None:
            pressures = self._calculate_pressures(
                {
                    "inflation_rate": state.inflation_rate,
                    "interest_rate": state.interest_rate,
                    "unemployment_rate": state.unemployment_rate,
                    "oil_index": state.oil_index,
                    "consumer_confidence": state.consumer_confidence,
                    "supply_chain_index": state.supply_chain_index,
                    "seasonal_index": state.seasonal_index,
                }
            )
        return {
            "day": state.day,
            "inflation_rate": state.inflation_rate,
            "interest_rate": state.interest_rate,
            "unemployment_rate": state.unemployment_rate,
            "oil_index": state.oil_index,
            "consumer_confidence": state.consumer_confidence,
            "supply_chain_index": state.supply_chain_index,
            "seasonal_index": state.seasonal_index,
            "basket_price_pressure": pressures["basket_price_pressure"],
            "layoff_pressure": pressures["layoff_pressure"],
            "wage_pressure": pressures["wage_pressure"],
        }

    # ── Backward-compat shim (legacy /economy/daily-brief) ────────────────────

    def run_daily_update(self, db: Session) -> dict[str, Any]:
        """Determine next unprocessed day and run economy for it."""
        latest = db.query(EconomyState).order_by(EconomyState.day.desc()).first()
        next_day = (latest.day + 1) if latest is not None else 1
        return self.process_next_day_economy(next_day, db)


    def _basket_price_changes(self, inflation: float, oil_delta: float, confidence: float) -> dict[str, float]:
        inflation_factor = inflation - 2.0
        confidence_factor = (confidence - 100.0) * 0.01

        return {
            "essentials": round(self._clamp(0.20 * inflation_factor + 0.03 * oil_delta + self.rng.uniform(-0.5, 0.5), -3.0, 4.0), 2),
            "protein": round(self._clamp(0.28 * inflation_factor + 0.02 * oil_delta + self.rng.uniform(-0.7, 0.7), -4.0, 5.0), 2),
            "produce": round(self._clamp(0.25 * inflation_factor + self.rng.uniform(-1.0, 1.0), -5.0, 6.0), 2),
            "convenience": round(
                self._clamp(0.34 * inflation_factor + 0.5 * confidence_factor + self.rng.uniform(-0.6, 0.6), -4.0, 5.0),
                2,
            ),
        }

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
