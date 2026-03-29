"""app/models/deal_template.py — Step 13: Co-op Deals System.

DealTemplate defines a reusable system-generated co-op opportunity type.

Templates are seeded at startup and never created directly by players.  Each
template describes:
  - which roles must be present (e.g. ["chef", "delivery_driver"])
  - which fixed split presets are allowed (e.g. [[50,50],[60,40]])
  - the base XGP payout value — macro-adjusted at deal creation / completion
  - optional regional bias and basket-dependency sensitivity factors

Economic context:
  Templates are the "job board" of the co-op economy.
  They make specific jobs and business types socially meaningful because only
  a player with the right role can participate.
  confidence_sensitivity links macro health to deal attractiveness.
  basket_dependency_json ties deal profitability to current basket price pressure,
  so produce shortages genuinely benefit fruit_shop owners.
"""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, Numeric, String, Text, func

from app.db.database import Base


class DealTemplate(Base):
    """System-generated co-op deal type.  Seeded at startup; never player-created."""

    __tablename__ = "deal_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Stable string key used by the API and engine.  e.g. "festival_food_rush".
    # Never changes after seeding; used as the canonical reference.
    template_id = Column(String(60), nullable=False, unique=True, index=True)

    display_name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)

    # JSON-encoded list of required role strings.
    # e.g. '["chef", "delivery_driver"]'
    # Role identifiers must match player.main_job or business_id strings.
    required_roles_json = Column(Text, nullable=False)

    # JSON-encoded list of allowed split preset arrays.
    # e.g. '[[50,50],[60,40],[40,60]]'
    # Each inner list must sum to 100 and match role count.
    allowed_split_presets_json = Column(Text, nullable=False)

    # Base XGP payout before any macro adjustment.
    # The engine multiplies this by a clamped macro multiplier at completion time.
    base_payout_xgp = Column(Numeric(10, 2), nullable=False)

    # Hours each participant must commit.  Used in future scheduling layers.
    # MVP does not enforce hours — tracked for display and future checks.
    hours_required_per_participant = Column(Integer, nullable=False, default=2)

    # Soft regional preference for where this deal is likely to appear.
    # None = available everywhere.  "downtown" / "suburban" = regional routing.
    region_bias = Column(String(40), nullable=True)

    # How much consumer confidence shifts the final payout multiplier.
    # 0.0 = no sensitivity.  0.25 = moderate.  1.0 = very sensitive.
    # Used in: confidence_boost = ((confidence - 50) / 100) * sensitivity
    confidence_sensitivity = Column(Float, nullable=False, default=0.0)

    # JSON-encoded basket weighting for payout price pressure.
    # e.g. '{"produce": 1.0}' means produce price deviation scales payout.
    # None = no basket dependency.
    basket_dependency_json = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
