"""Phase 3-C Player Absence Handling: last_seen_at / last_settlement_at.

Revision ID: 20260430_0034_player_absence_anchors
Revises: 20260430_0033_player_notification_log
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260430_0034_player_absence_anchors"
down_revision: Union[str, Sequence[str], None] = "20260430_0033_player_notification_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "players", sa.Column("last_settlement_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("players", "last_settlement_at")
    op.drop_column("players", "last_seen_at")
