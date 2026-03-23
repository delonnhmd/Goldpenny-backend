import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class HousingAction(Base):
    """Immutable audit log for all housing-related actions.

    action_type values:
        move_in | pay_housing_cost | make_debt_payment |
        maintenance_event | move_out | default_event
    """

    __tablename__ = "housing_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    housing_id = Column(UUID(as_uuid=True), nullable=True)
    action_type = Column(String(40), nullable=False)
    day = Column(Integer, nullable=False)
    amount = Column(Numeric(10, 2), nullable=True)              # total housing cost
    property_tax_amount = Column(Numeric(10, 2), nullable=True)
    maintenance_amount = Column(Numeric(10, 2), nullable=True)
    debt_payment_amount = Column(Numeric(10, 2), nullable=True)
    stress_change = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
