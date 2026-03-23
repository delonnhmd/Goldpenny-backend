from sqlalchemy import Column, DateTime, Integer, String, func

from app.db.database import Base


class GameState(Base):
    """
    Singleton-like global state table.  Only one active row is expected in MVP.

    Tracks the current in-game day and its lifecycle status so all parts of the
    backend share a single source of truth for game time.

    The engine creates this row automatically on first access (get_or_create_game_state).
    """

    __tablename__ = "game_states"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # The current in-game day number.  Starts at 1.  Incremented by advance_global_day().
    current_day = Column(Integer, nullable=False, default=1, index=True)

    # Real-world timestamp when the current in-game day was opened.
    # Preserved from original model name for backward compatibility.
    real_world_timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Step 3: explicit day_started_at for the daily engine (mirrors real_world_timestamp).
    day_started_at = Column(DateTime(timezone=True), nullable=True)

    # Lifecycle status of the current day.
    # "open"     — players can work and act normally
    # "settling" — transitional state (reserved for future global settlement)
    # "closed"   — day is fully closed (reserved for future global settlement)
    day_status = Column(String(20), nullable=False, default="open")

    economy_seed = Column(Integer, nullable=False, default=0)
    # Tracks which in-game day the economy engine has already processed.
    # Prevents duplicate economy processing. Added in Step 5.
    economy_processed_for_day = Column(Integer, nullable=True, default=None)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
