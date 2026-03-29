from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db.database import Base


class SectorIndex(Base):
    __tablename__ = "sector_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, nullable=False, index=True)
    sector_name = Column(String, nullable=False, index=True)
    sector_index_value = Column(Float, nullable=False, default=100.0)
    daily_change_percent = Column(Float, nullable=False, default=0.0)
    macro_driver = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
