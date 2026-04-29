"""Phase 3-C Step 1: player push notification tokens.

Revision ID: 20260429_0031_player_push_tokens
Revises: 20260428_0030_realworld_cost_breaker
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260429_0031_player_push_tokens"
down_revision: Union[str, Sequence[str], None] = "20260428_0030_realworld_cost_breaker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_push_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("push_token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "push_token", name="uq_player_push_tokens_player_id_push_token"),
        sa.UniqueConstraint("push_token", name="uq_player_push_tokens_push_token"),
    )
    op.create_index(
        "ix_player_push_tokens_player_id",
        "player_push_tokens",
        ["player_id"],
    )
    op.create_index(
        "ix_player_push_tokens_player_platform",
        "player_push_tokens",
        ["player_id", "platform"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_push_tokens_player_platform", table_name="player_push_tokens")
    op.drop_index("ix_player_push_tokens_player_id", table_name="player_push_tokens")
    op.drop_table("player_push_tokens")
