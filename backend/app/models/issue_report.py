"""Step 70 — Issue / bug reports submitted by players during soft launch.

category: 'bug' | 'friction' | 'ui' | 'balance' | 'other'
severity: 'low' | 'medium' | 'high' | 'blocker'
extra_context_json holds arbitrary JSON from the client (device info, route, etc.).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class IssueReport(Base):
    __tablename__ = "issue_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id = Column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(64), nullable=True)
    game_day = Column(Integer, nullable=True)
    description = Column(Text, nullable=False)
    category = Column(String(40), nullable=True)   # bug | friction | ui | balance | other
    severity = Column(String(20), nullable=True)   # low | medium | high | blocker
    extra_context_json = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
