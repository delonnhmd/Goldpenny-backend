"""job market pressure employment fields

Revision ID: 20260316_0007_job_market
Revises: 20260316_0006_housing_region
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260316_0007_job_market"
down_revision: Union[str, Sequence[str], None] = "20260316_0006_housing_region"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(col.get("name") == column_name for col in columns)


def upgrade() -> None:
    table = "player_employment_states"

    if not _has_column(table, "job_status"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN job_status VARCHAR(20) NOT NULL DEFAULT 'employed'"
        )
    if not _has_column(table, "promotion_eligible_flag"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN promotion_eligible_flag BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if not _has_column(table, "promotion_count"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN promotion_count INTEGER NOT NULL DEFAULT 0"
        )
    if not _has_column(table, "last_raise_pct"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN last_raise_pct NUMERIC(6,2) NOT NULL DEFAULT 0"
        )
    if not _has_column(table, "last_employment_event"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN last_employment_event VARCHAR(40)"
        )
    if not _has_column(table, "opportunity_score"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN opportunity_score NUMERIC(8,4) NOT NULL DEFAULT 1.0"
        )
    if not _has_column(table, "layoff_event_flag"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN layoff_event_flag BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if not _has_column(table, "promotion_chance_pct"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN promotion_chance_pct NUMERIC(6,2) NOT NULL DEFAULT 0"
        )
    if not _has_column(table, "wage_adjustment_pct"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN wage_adjustment_pct NUMERIC(6,2) NOT NULL DEFAULT 0"
        )
    if not _has_column(table, "employment_evaluated_flag"):
        op.execute(
            "ALTER TABLE player_employment_states "
            "ADD COLUMN employment_evaluated_flag BOOLEAN NOT NULL DEFAULT FALSE"
        )


def downgrade() -> None:
    table = "player_employment_states"
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS employment_evaluated_flag")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS wage_adjustment_pct")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS promotion_chance_pct")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS layoff_event_flag")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS opportunity_score")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS last_employment_event")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS last_raise_pct")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS promotion_count")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS promotion_eligible_flag")
    op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS job_status")
