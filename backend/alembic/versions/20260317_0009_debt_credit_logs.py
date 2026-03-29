"""debt_credit_logs table.

Revision ID: 20260317_0009_debt_credit
Revises: 20260316_0008_basket_consumption
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260317_0009_debt_credit"
down_revision: Union[str, Sequence[str], None] = "20260316_0008_basket_consumption"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "debt_credit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("opening_debt_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("payment_due_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("payment_made_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("interest_added_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("ending_debt_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="no_debt"),
        sa.Column("opening_credit_score", sa.Integer(), nullable=False),
        sa.Column("credit_score_change", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ending_credit_score", sa.Integer(), nullable=False),
        sa.Column("delinquency_flag", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("notes_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("player_id", "day", name="uq_debt_credit_log_player_day"),
    )

    op.create_index("ix_debt_credit_logs_player_id", "debt_credit_logs", ["player_id"])
    op.create_index("ix_debt_credit_logs_day", "debt_credit_logs", ["day"])

    # Enable RLS so policies can be layered without another schema revision.
    op.execute("ALTER TABLE debt_credit_logs ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_debt_credit_logs_day", table_name="debt_credit_logs")
    op.drop_index("ix_debt_credit_logs_player_id", table_name="debt_credit_logs")
    op.drop_table("debt_credit_logs")
