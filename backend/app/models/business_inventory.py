import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class BusinessInventory(Base):
    """Input inventory held by a business.

    Separate from player household inventory — you must explicitly purchase
    stock for a business before it can operate.

    One row per (business, basket_name) pair; quantity is updated in place.
    """

    __tablename__ = "business_inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    basket_name = Column(String(60), nullable=False)   # e.g. "produce_basket"
    quantity = Column(Integer, nullable=False, default=0)
    freshness = Column(Float, nullable=False, default=1.0)  # 0.0 – 1.0
    created_day = Column(Integer, nullable=True)   # in-game day first bought

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    business = relationship("Business", back_populates="inventory")
