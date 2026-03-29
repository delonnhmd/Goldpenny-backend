from sqlalchemy import Column, DateTime, Float, Integer, String, func

from app.db.database import Base

# Default starting values for in-game day 1.
_DEFAULTS = {
    "inflation_rate": 2.5,
    "interest_rate": 4.5,
    "unemployment_rate": 5.0,
    "oil_index": 100.0,
    "consumer_confidence": 100.0,
    "supply_chain_index": 100.0,
    "seasonal_index": 100.0,
}


class EconomyState(Base):
    """Active macro-economy state for each in-game day.

    Uses tablename ``economy_state`` (singular) so it coexists with the legacy
    ``economy_states`` table without schema conflicts during iterative dev.
    """

    __tablename__ = "economy_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, nullable=False, unique=True, index=True)
    # ── Macro variables ──────────────────────────────────────────────────────
    inflation_rate = Column(Float, nullable=False, default=_DEFAULTS["inflation_rate"])
    interest_rate = Column(Float, nullable=False, default=_DEFAULTS["interest_rate"])
    unemployment_rate = Column(Float, nullable=False, default=_DEFAULTS["unemployment_rate"])
    oil_index = Column(Float, nullable=False, default=_DEFAULTS["oil_index"])
    consumer_confidence = Column(Float, nullable=False, default=_DEFAULTS["consumer_confidence"])
    supply_chain_index = Column(Float, nullable=False, default=_DEFAULTS["supply_chain_index"])
    seasonal_index = Column(Float, nullable=False, default=_DEFAULTS["seasonal_index"])
    # ── Metadata ─────────────────────────────────────────────────────────────
    event_count = Column(Integer, nullable=False, default=0)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
