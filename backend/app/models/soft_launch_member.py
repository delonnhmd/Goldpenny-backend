"""Step 70 — Soft launch cohort membership.

One row per user who has successfully joined a soft launch cohort.
user_id is unique — a user can only be in one cohort.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class SoftLaunchMember(Base):
    __tablename__ = "soft_launch_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    invite_code_used = Column(String(64), nullable=True)
    cohort_tag = Column(String(40), nullable=False, default="soft_launch_v1")
    is_approved = Column(Boolean, nullable=False, default=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
