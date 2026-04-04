"""Step 84: missed-shift, meal tracking, and weekend day-state fields.

Revision ID: 20260403_0025_missed_shift_rideshare_weekend
Revises: 20260402_0024_gameplay_transparency
Create Date: 2026-04-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260403_0025_missed_shift_rideshare_weekend"
down_revision: Union[str, Sequence[str], None] = "20260402_0024_gameplay_transparency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_daily_states",
        sa.Column("missed_shift", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "player_daily_states",
        sa.Column("meals_recorded", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_daily_states",
        sa.Column("survival_penalty_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("player_daily_states", "survival_penalty_applied")
    op.drop_column("player_daily_states", "meals_recorded")
    op.drop_column("player_daily_states", "missed_shift")
