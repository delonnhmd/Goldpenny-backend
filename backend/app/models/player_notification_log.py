"""Phase 3-C Push Scheduling: notification dispatch log.

Tracks every daily-loop push attempt so the scheduler can de-duplicate
sends across runs (the cron fires every 5 minutes and a window is
several minutes wide).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class PlayerNotificationLog(Base):
    __tablename__ = "player_notification_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = Column(String(60), nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False, default="sent")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "notification_type",
            "scheduled_for",
            name="uq_player_notif_log_player_type_scheduled",
        ),
        Index(
            "ix_player_notif_log_player_type_scheduled",
            "player_id",
            "notification_type",
            "scheduled_for",
        ),
    )
