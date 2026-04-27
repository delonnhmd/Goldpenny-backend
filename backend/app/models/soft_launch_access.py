"""Step 70 — Soft launch invite code catalogue.

Rows here are pre-provisioned invite codes. When a user redeems a code
the use_count is incremented.  Admins can deactivate codes without
touching user memberships.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class SoftLaunchAccess(Base):
    __tablename__ = "soft_launch_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invite_code = Column(String(64), unique=True, nullable=False, index=True)
    cohort_tag = Column(String(40), nullable=False, default="soft_launch_v1")
    description = Column(Text, nullable=True)
    max_uses = Column(Integer, nullable=False, default=1)
    use_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
