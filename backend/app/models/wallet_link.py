"""Wallet address link — preparation for future on-chain claim step."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class WalletLink(Base):
    __tablename__ = "wallet_links"
    __table_args__ = (
        # Only one verified wallet per player per chain for MVP.
        UniqueConstraint("player_id", "chain_name", name="uq_wallet_link_player_chain"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wallet_address = Column(String(255), nullable=False)
    chain_name = Column(String(50), nullable=False, default="base")
    is_verified = Column(Boolean, nullable=False, default=False)
    linked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
