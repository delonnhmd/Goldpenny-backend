"""Phase 3-D Step 3: player black swan event log.

Revision ID: 20260501_0035_player_black_swan_event
Revises: 20260430_0034_player_absence_anchors
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260501_0035_player_black_swan_event"
down_revision: Union[str, Sequence[str], None] = "20260430_0034_player_absence_anchors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_black_swan_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity_score", sa.Numeric(10, 4), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["daily_economy_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "day", name="uq_player_black_swan_event_player_day"),
    )
    op.create_index("ix_player_black_swan_event_player_id", "player_black_swan_event", ["player_id"])
    op.create_index("ix_player_black_swan_event_day", "player_black_swan_event", ["day"])
    op.create_index("ix_player_black_swan_event_event_type", "player_black_swan_event", ["event_type"])
    op.create_index("ix_player_black_swan_event_source_event_id", "player_black_swan_event", ["source_event_id"])
    op.create_index("ix_player_black_swan_event_seen_at", "player_black_swan_event", ["seen_at"])
    op.create_index(
        "ix_player_black_swan_event_pending",
        "player_black_swan_event",
        ["player_id", "seen_at", "day"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_black_swan_event_pending", table_name="player_black_swan_event")
    op.drop_index("ix_player_black_swan_event_seen_at", table_name="player_black_swan_event")
    op.drop_index("ix_player_black_swan_event_source_event_id", table_name="player_black_swan_event")
    op.drop_index("ix_player_black_swan_event_event_type", table_name="player_black_swan_event")
    op.drop_index("ix_player_black_swan_event_day", table_name="player_black_swan_event")
    op.drop_index("ix_player_black_swan_event_player_id", table_name="player_black_swan_event")
    op.drop_table("player_black_swan_event")
