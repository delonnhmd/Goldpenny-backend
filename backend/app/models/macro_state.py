"""
MacroState — global macroeconomic state used to drive daily basket price movement.

Design principles:
  - One row per in-game day in MVP.  The most recently created row for a given
    day_number is considered authoritative if duplicates ever occur.
  - All fields have safe defaults so the engine can auto-create a day-1 row
    without any manual admin input.
  - is_active lets operators archive old rows without deleting them.

Economic intent:
  MacroState is the global "weather" of the economy.  All players see the same
  macro conditions.  The values in this row drive basket price changes through
  macro_engine.calculate_basket_daily_change_percent().

  Macro state is global — one shared world economy.
  Basket prices are the first visible output of the macro layer.
  Daily capped movement (+/-5%) prevents unrealistic chaos.

  Typical flow:
    Day N:
      1. Admin advances global day to N.
      2. MacroState for day N is auto-created with defaults.
      3. Admin (or future event engine) updates oil_index / supply_chain_stress.
      4. Admin calls POST /macro/admin/apply-daily-basket-update.
      5. Each basket's price_index shifts by up to ±5%.
      6. Players buying baskets now pay the updated price.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, func

from app.db.database import Base


class MacroState(Base):
    """Global macroeconomic state for one in-game day.

    All numeric fields are stored as Numeric(10,4) to give enough precision
    for the price-movement formula while keeping values human-readable.
    """

    __tablename__ = "macro_states"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # The in-game day this row describes.  Should be unique per active row.
    day_number = Column(Integer, nullable=False, index=True)

    # ── Core macro variables ──────────────────────────────────────────────────

    # Annual inflation rate as a percentage.  2.0 = 2% (normal).
    # Positive inflation raises basket prices; negative = deflation.
    inflation = Column(Numeric(10, 4), nullable=False, default=2.0)

    # Central bank interest rate as a percentage.  4.0 = 4% (normal).
    # Higher rates slow demand; affects job wages and housing costs in future steps.
    interest_rate = Column(Numeric(10, 4), nullable=False, default=4.0)

    # Unemployment rate as a percentage.  5.0 = 5% (normal).
    # High unemployment suppresses consumer confidence and basket demand.
    unemployment = Column(Numeric(10, 4), nullable=False, default=5.0)

    # Oil / energy price index.  100.0 = baseline.
    # Oil affects transport and production costs for all baskets.
    # Produce and protein baskets are more oil-sensitive (refrigeration / shipping).
    oil_index = Column(Numeric(10, 4), nullable=False, default=100.0)

    # Consumer confidence index.  50.0 = neutral (0 = panic, 100 = euphoric).
    # Low confidence pushes prices up (precautionary buying) or triggers supply shocks.
    consumer_confidence = Column(Numeric(10, 4), nullable=False, default=50.0)

    # Supply chain disruption score.  0.0 = none, 100.0 = severe disruption.
    # High supply chain stress strongly raises produce and protein prices.
    supply_chain_stress = Column(Numeric(10, 4), nullable=False, default=0.0)

    # Soft-delete flag.  Inactive rows are kept for audit; engine uses active rows.
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
