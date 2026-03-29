"""business daily operations mvp schema

Revision ID: 20260316_0005_business_ops
Revises: 20260316_0004
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260316_0005_business_ops"
down_revision: Union[str, Sequence[str], None] = "20260316_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # Player business schema alignment for business daily operations MVP.
    op.execute("ALTER TABLE player_businesses DROP CONSTRAINT IF EXISTS uq_pb_player")
    op.execute(
        "ALTER TABLE player_businesses "
        "ADD COLUMN IF NOT EXISTS region VARCHAR(40) NOT NULL DEFAULT 'suburban'"
    )
    op.execute(
        "ALTER TABLE player_businesses "
        "ADD COLUMN IF NOT EXISTS reputation INTEGER NOT NULL DEFAULT 50"
    )
    op.execute(
        "ALTER TABLE player_businesses "
        "ADD COLUMN IF NOT EXISTS cash_reserve_xgp NUMERIC(14,2)"
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_player_businesses_player_id'
            ) THEN
                ALTER TABLE player_businesses
                ADD CONSTRAINT fk_player_businesses_player_id
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )

    if not _table_exists(bind, "business_daily_logs"):
        op.create_table(
            "business_daily_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("gross_revenue_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("input_cost_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("fuel_cost_xgp", sa.Numeric(14, 4), nullable=True),
            sa.Column("spoilage_cost_xgp", sa.Numeric(14, 4), nullable=True),
            sa.Column("overhead_cost_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("net_profit_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("demand_score", sa.Numeric(8, 4), nullable=False),
            sa.Column("utilization_pct", sa.Numeric(8, 4), nullable=False),
            sa.Column("notes_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["business_id"], ["player_businesses.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("business_id", "day", name="uq_business_daily_logs_business_day"),
        )
        op.create_index("ix_business_daily_logs_business_id", "business_daily_logs", ["business_id"], unique=False)
        op.create_index("ix_business_daily_logs_player_id", "business_daily_logs", ["player_id"], unique=False)
        op.create_index("ix_business_daily_logs_day", "business_daily_logs", ["day"], unique=False)

    if not _table_exists(bind, "business_ledger_entries"):
        op.create_table(
            "business_ledger_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("amount_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("direction", sa.String(length=10), nullable=False),
            sa.Column("memo", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["business_id"], ["player_businesses.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_business_ledger_entries_business_id", "business_ledger_entries", ["business_id"], unique=False)
        op.create_index("ix_business_ledger_entries_day", "business_ledger_entries", ["day"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "business_ledger_entries"):
        op.drop_index("ix_business_ledger_entries_day", table_name="business_ledger_entries")
        op.drop_index("ix_business_ledger_entries_business_id", table_name="business_ledger_entries")
        op.drop_table("business_ledger_entries")

    if _table_exists(bind, "business_daily_logs"):
        op.drop_index("ix_business_daily_logs_day", table_name="business_daily_logs")
        op.drop_index("ix_business_daily_logs_player_id", table_name="business_daily_logs")
        op.drop_index("ix_business_daily_logs_business_id", table_name="business_daily_logs")
        op.drop_table("business_daily_logs")

    op.execute("ALTER TABLE player_businesses DROP CONSTRAINT IF EXISTS fk_player_businesses_player_id")
    op.execute("ALTER TABLE player_businesses DROP COLUMN IF EXISTS cash_reserve_xgp")
    op.execute("ALTER TABLE player_businesses DROP COLUMN IF EXISTS reputation")
    op.execute("ALTER TABLE player_businesses DROP COLUMN IF EXISTS region")

    # Best-effort restoration of legacy one-business-per-player uniqueness.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_pb_player'
            ) THEN
                BEGIN
                    ALTER TABLE player_businesses
                    ADD CONSTRAINT uq_pb_player UNIQUE (player_id);
                EXCEPTION
                    WHEN unique_violation THEN
                        NULL;
                END;
            END IF;
        END $$;
        """
    )
