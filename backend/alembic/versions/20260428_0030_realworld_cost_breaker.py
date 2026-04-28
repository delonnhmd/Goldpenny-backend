"""Phase 3-B-1 task 5: real-world generation cost breaker tables.

Revision ID: 20260428_0030_realworld_cost_breaker
Revises: 20260427_0029_realworld_event_fields
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260428_0030_realworld_cost_breaker"
down_revision: Union[str, Sequence[str], None] = "20260427_0029_realworld_event_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "realworld_generation_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_realworld_generation_costs_event_id",
        "realworld_generation_costs",
        ["event_id"],
    )
    op.create_index(
        "ix_realworld_generation_costs_recorded_at",
        "realworld_generation_costs",
        ["recorded_at"],
    )

    op.create_table(
        "cost_breaker_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("monthly_cost_per_mau", sa.Numeric(10, 6), nullable=False),
        sa.Column("threshold_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cost_breaker_alerts_created_at",
        "cost_breaker_alerts",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_breaker_alerts_created_at", table_name="cost_breaker_alerts")
    op.drop_table("cost_breaker_alerts")
    op.drop_index(
        "ix_realworld_generation_costs_recorded_at",
        table_name="realworld_generation_costs",
    )
    op.drop_index(
        "ix_realworld_generation_costs_event_id",
        table_name="realworld_generation_costs",
    )
    op.drop_table("realworld_generation_costs")
