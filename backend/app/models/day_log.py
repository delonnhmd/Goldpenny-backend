import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class DayLog(Base):
    __tablename__ = "day_logs"
    __table_args__ = (UniqueConstraint("player_id", "day", name="uq_day_logs_player_day"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(Integer, nullable=False, index=True)

    starting_cash = Column(Numeric(12, 2), nullable=False)
    ending_cash = Column(Numeric(12, 2), nullable=False)

    starting_health = Column(Integer, nullable=False)
    ending_health = Column(Integer, nullable=False)

    starting_stress = Column(Integer, nullable=False)
    ending_stress = Column(Integer, nullable=False)

    starting_fatigue = Column(Float, nullable=False)
    ending_fatigue = Column(Float, nullable=False)

    hours_worked = Column(Integer, nullable=False, default=0)
    income_earned = Column(Numeric(12, 2), nullable=False, default=0)
    actions_taken = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
