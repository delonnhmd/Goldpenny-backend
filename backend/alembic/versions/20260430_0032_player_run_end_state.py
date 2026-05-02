"""Phase 3-C Step 3: player run end state.

Revision ID: 20260430_0032_player_run_end_state
Revises: 20260429_0031_player_push_tokens
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260430_0032_player_run_end_state"
down_revision: Union[str, Sequence[str], None] = "20260429_0031_player_push_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("run_status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("players", sa.Column("run_ended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("players", sa.Column("run_end_day", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("run_end_reason", sa.String(length=80), nullable=True))
    op.add_column("players", sa.Column("run_end_summary_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "run_end_summary_json")
    op.drop_column("players", "run_end_reason")
    op.drop_column("players", "run_end_day")
    op.drop_column("players", "run_ended_at")
    op.drop_column("players", "run_status")
