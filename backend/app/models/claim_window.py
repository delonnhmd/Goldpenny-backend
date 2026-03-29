"""Monthly reward cycle / claim window settings."""

from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db.database import Base


class ClaimWindow(Base):
    __tablename__ = "claim_windows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month_key = Column(String(7), nullable=False, unique=True, index=True)  # "YYYY-MM"

    # Lifecycle status: draft → open → closed → finalized
    status = Column(String(20), nullable=False, default="draft")

    # Pool accounting
    total_pool = Column(Float, nullable=False, default=100_000.0)
    total_approved = Column(Float, nullable=False, default=0.0)
    total_claimed = Column(Float, nullable=False, default=0.0)

    # Per-player rules
    min_claim_threshold = Column(Float, nullable=False, default=25.0)
    max_claim_per_player = Column(Float, nullable=False, default=200.0)

    # Optional time gates (not enforced in Step 5.5 — placeholder for future)
    opens_at = Column(DateTime(timezone=True), nullable=True)
    closes_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
