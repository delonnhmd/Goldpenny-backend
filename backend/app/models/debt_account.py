import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class DebtAccount(Base):
    """Structured debt obligation for a player.

    debt_type values:   mortgage | personal_debt | emergency_debt
    delinquency_status: current | late | delinquent | severe
    """

    __tablename__ = "debt_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    debt_type = Column(String(40), nullable=False)              # mortgage | personal_debt | emergency_debt
    principal_balance = Column(Numeric(14, 2), nullable=False)
    interest_rate = Column(Float, nullable=False)               # annual %, e.g. 6.0
    minimum_daily_payment = Column(Numeric(10, 2), nullable=False)
    missed_payment_count = Column(Integer, nullable=False, default=0)
    delinquency_status = Column(String(20), nullable=False, default="current")
    originated_day = Column(Integer, nullable=False)
    last_payment_day = Column(Integer, nullable=True)
    # ── Step 8b: delinquency and payment tracking ─────────────────────────────
    cumulative_interest_paid = Column(Numeric(12, 2), nullable=False, default=0)
    cumulative_principal_paid = Column(Numeric(12, 2), nullable=False, default=0)
    consecutive_missed_payments = Column(Integer, nullable=False, default=0)
    penalty_rate_modifier = Column(Float, nullable=False, default=1.0)
    last_delinquency_day = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
