"""Phase 3-C Push Scheduling: player_notification_log table.

Revision ID: 20260430_0033_player_notification_log
Revises: 20260430_0032_player_run_end_state
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260430_0033_player_notification_log"
down_revision: Union[str, Sequence[str], None] = "20260430_0032_player_run_end_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_notification_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=60), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="sent"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "player_id",
            "notification_type",
            "scheduled_for",
            name="uq_player_notif_log_player_type_scheduled",
        ),
    )
    op.create_index(
        "ix_player_notification_log_player_id",
        "player_notification_log",
        ["player_id"],
    )
    op.create_index(
        "ix_player_notif_log_player_type_scheduled",
        "player_notification_log",
        ["player_id", "notification_type", "scheduled_for"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_notif_log_player_type_scheduled", table_name="player_notification_log")
    op.drop_index("ix_player_notification_log_player_id", table_name="player_notification_log")
    op.drop_table("player_notification_log")
