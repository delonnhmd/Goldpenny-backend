"""Step 92: per-job progression tracks (safe-mode XP/level storage).

Revision ID: 20260407_0026_player_job_progression_tracks
Revises: 20260403_0025_missed_shift_rideshare_weekend
Create Date: 2026-04-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260407_0026_player_job_progression_tracks"
down_revision: Union[str, Sequence[str], None] = "20260403_0025_missed_shift_rideshare_weekend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_job_progressions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_key", sa.String(length=60), nullable=False),
        sa.Column("skill_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("xp_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_to_next_level", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("promotion_tier", sa.String(length=30), nullable=False, server_default="Junior"),
        sa.Column("shifts_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_worked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "player_id",
            "job_key",
            name="uq_player_job_progression_player_job",
        ),
    )
    op.create_index(
        "ix_player_job_progressions_player_id",
        "player_job_progressions",
        ["player_id"],
    )
    op.create_index(
        "ix_player_job_progressions_job_key",
        "player_job_progressions",
        ["job_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_job_progressions_job_key", table_name="player_job_progressions")
    op.drop_index("ix_player_job_progressions_player_id", table_name="player_job_progressions")
    op.drop_table("player_job_progressions")
