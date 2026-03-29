import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class JobAction(Base):
    """Immutable record of a single work shift performed by a player."""

    __tablename__ = "job_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_name = Column(String(60), nullable=False)
    job_type = Column(String(10), nullable=False)          # "main" or "side"
    shift_number = Column(Integer, nullable=False)         # 1 or 2 within the day
    day = Column(Integer, nullable=False)                  # in-game economy day
    hours_worked = Column(Integer, nullable=False)
    base_hourly_pay = Column(Numeric(10, 4), nullable=False)
    productivity = Column(Float, nullable=False)
    earned_cash = Column(Numeric(12, 2), nullable=False)
    stress_change = Column(Integer, nullable=False)
    health_change = Column(Integer, nullable=False)
    fatigue_change = Column(Float, nullable=False)
    overtime_penalty_applied = Column(Boolean, nullable=False, default=False)
    hours_remaining_after = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    player = relationship("Player", back_populates="job_actions")
