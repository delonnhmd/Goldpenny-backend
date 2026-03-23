"""app/models/housing_region.py — Step 7: Housing Region definitions.

Two regions for MVP:
  - suburban  (cheaper, calmer, stress_modifier = -1)
  - downtown  (more expensive, more pressure, stress_modifier = +2)

This table acts as the authoritative registry of valid regions.
Seeding is idempotent (get_or_seed_default_housing_regions in housing_engine.py).

Economic context:
  Region choice is the first fixed recurring cost layer for a player.
  Suburban is cheaper and calmer — a safe starting point.
  Downtown costs more and adds stress but will offer more opportunity in later steps.
  This is a bridge toward commute, networking, and opportunity systems.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class HousingRegion(Base):
    """Registry row for a living region.  Two active rows seed on startup."""

    __tablename__ = "housing_regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Short stable identifier used as FK target in player and payment records.
    # e.g. "suburban", "downtown"
    region_id = Column(String(40), unique=True, nullable=False, index=True)

    # Human-readable label surfaced to the frontend.
    display_name = Column(String(80), nullable=False)

    # Daily XGP cost deducted at settlement time.
    # suburban = 18.0 XGP/day   (affordable baseline)
    # downtown = 35.0 XGP/day   (premium cost, reflects real financial pressure)
    daily_cost = Column(Numeric(10, 2), nullable=False)

    # Applied to player stress at settlement.
    # Negative = calming effect  (suburban = -1)
    # Positive = extra pressure  (downtown = +2)
    stress_modifier = Column(Integer, nullable=False)

    # Only active regions are surfaced to players.
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# Canonical seed data — used by get_or_seed_default_housing_regions().
DEFAULT_HOUSING_REGIONS: list[dict] = [
    {
        "region_id": "suburban",
        "display_name": "Suburban",
        "daily_cost": 18.0,
        "stress_modifier": -1,   # living here is calmer
        "is_active": True,
    },
    {
        "region_id": "downtown",
        "display_name": "Downtown",
        "daily_cost": 35.0,
        "stress_modifier": 2,    # premium cost adds pressure
        "is_active": True,
    },
]
