"""Player-owned business state."""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base


class PlayerBusiness(Base):
    """Active (or former) small business owned by a player."""

    __tablename__ = "player_businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owning player.
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Canonical business code (for example: fruit_shop, food_truck).
    business_id = Column(String(40), nullable=False, index=True)

    # Optional player-facing name.
    business_name = Column(String(120), nullable=True)

    # Region where the business operates. Uses player region by default.
    region = Column(String(40), nullable=False, default="suburban")

    # String level label used by Step 15 formulas (starter/cart/etc).
    level_key = Column(String(40), nullable=False, default="starter")

    # MVP tier/progression level.
    business_level = Column(Integer, nullable=False, default=1)

    # Business reputation score (bounded in service logic, stored as integer).
    reputation = Column(Integer, nullable=False, default=50)

    # Optional business reserve wallet for future maintenance/expansion systems.
    cash_reserve_xgp = Column(Numeric(14, 2), nullable=True)

    # Lifetime capital put into this business by the player.
    cash_invested_xgp = Column(Numeric(14, 4), nullable=False, default=0)

    # Inventory state (kept in business units, not player inventory units).
    inventory_produce_units = Column(Numeric(14, 4), nullable=False, default=0)
    inventory_essentials_units = Column(Numeric(14, 4), nullable=False, default=0)
    inventory_protein_units = Column(Numeric(14, 4), nullable=False, default=0)

    # Fruit shop pricing control. Enforced by service guardrails.
    fruit_markup_pct = Column(Numeric(8, 4), nullable=False, default=0.20)

    # Step 22: player-selectable operating mode and applied mini-upgrades.
    operating_mode = Column(String(40), nullable=True)
    upgrades_json = Column(Text, nullable=True, default="[]")

    # Game-day on which the player started this business.
    created_day = Column(Integer, nullable=False, default=0)

    # Game-day on which the player last ran an operation.
    last_operated_day = Column(Integer, nullable=True)
    # Date mirror for APIs that operate in date space.
    last_operated_on = Column(Date, nullable=True)

    # Step 11 counters retained for backward compatibility with existing business engine.
    times_operated_today = Column(Integer, nullable=False, default=0)
    lifetime_business_runs = Column(Integer, nullable=False, default=0)

    # False once the player closes the business.
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Step compatibility aliases expected by newer APIs/specs.
    business_type = synonym("business_id")
    tier = synonym("business_level")
    active_flag = synonym("is_active")
    region_key = synonym("region")
    level = synonym("level_key")

    daily_logs = relationship(
        "BusinessDailyLog",
        back_populates="business",
        order_by="BusinessDailyLog.created_at.desc()",
        cascade="all, delete-orphan",
    )
