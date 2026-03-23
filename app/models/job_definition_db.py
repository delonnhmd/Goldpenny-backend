"""Database-backed job definition table for core schema bootstrapping."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, Numeric, String, func

from app.db.database import Base


class JobDefinition(Base):
    __tablename__ = "job_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_code = Column(String(60), nullable=False, unique=True, index=True)
    title = Column(String(120), nullable=False)

    base_monthly_pay_xgp = Column(Numeric(14, 2), nullable=False)
    stability_pct = Column(Numeric(6, 2), nullable=False, default=0)
    growth_pct = Column(Numeric(6, 2), nullable=False, default=0)
    stress_pct = Column(Numeric(6, 2), nullable=False, default=0)
    promotion_threshold = Column(Integer, nullable=False, default=100)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

