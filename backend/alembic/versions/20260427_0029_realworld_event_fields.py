"""Phase 3-B-1 (task 2): real-world-anchored fields on daily_economy_events.

Additive only — all new columns are nullable except ``is_realworld_anchored``,
which has a server default of ``false`` so existing rows backfill cleanly.

Revision ID: 20260427_0029_realworld_event_fields
Revises: 20260414_0028_supabase_player_user_link
Create Date: 2026-04-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260427_0029_realworld_event_fields"
down_revision: Union[str, Sequence[str], None] = "20260414_0028_supabase_player_user_link"
branch_labels = None
depends_on = None


# JSON-on-Postgres-as-JSONB / JSON-on-SQLite — same shape as the model column.
_JSON_PORTABLE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


_NEW_COLUMNS = (
    "is_realworld_anchored",
    "source_summary",
    "source_urls",
    "generated_at",
    "affected_sectors",
    "duration_days",
    "magnitude",
)


def upgrade() -> None:
    op.add_column(
        "daily_economy_events",
        sa.Column(
            "is_realworld_anchored",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("daily_economy_events", sa.Column("source_summary", sa.Text(), nullable=True))
    op.add_column("daily_economy_events", sa.Column("source_urls", _JSON_PORTABLE, nullable=True))
    op.add_column(
        "daily_economy_events",
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("daily_economy_events", sa.Column("affected_sectors", _JSON_PORTABLE, nullable=True))
    op.add_column("daily_economy_events", sa.Column("duration_days", sa.Integer(), nullable=True))
    op.add_column("daily_economy_events", sa.Column("magnitude", sa.Float(), nullable=True))


def downgrade() -> None:
    # Drop in reverse order of upgrade for symmetry; order doesn't matter for
    # column drops on Postgres but keeps the diff readable.
    for col in reversed(_NEW_COLUMNS):
        op.drop_column("daily_economy_events", col)
