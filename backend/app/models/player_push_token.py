import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerPushToken(Base):
    __tablename__ = "player_push_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    push_token = Column(String(255), nullable=False)
    platform = Column(String(20), nullable=False, default="unknown")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("player_id", "push_token", name="uq_player_push_tokens_player_id_push_token"),
        UniqueConstraint("push_token", name="uq_player_push_tokens_push_token"),
        Index("ix_player_push_tokens_player_platform", "player_id", "platform"),
    )
