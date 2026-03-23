"""Step 69: retention engine columns on player_daily_states

Adds two nullable TEXT columns to player_daily_states for persisting
next-day pressure flags and carryover opportunity data.  Uses IF NOT EXISTS
so the migration is safe to re-run against older schemas.

Revision ID: 20260323_0020_retention_engine
Revises: 85854026afad
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260323_0020_retention_engine"
down_revision: Union[str, Sequence[str], None] = "85854026afad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE player_daily_states "
        "ADD COLUMN IF NOT EXISTS retention_flags_json TEXT"
    )
    op.execute(
        "ALTER TABLE player_daily_states "
        "ADD COLUMN IF NOT EXISTS carryover_opportunities_json TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE player_daily_states "
        "DROP COLUMN IF EXISTS retention_flags_json"
    )
    op.execute(
        "ALTER TABLE player_daily_states "
        "DROP COLUMN IF EXISTS carryover_opportunities_json"
    )
