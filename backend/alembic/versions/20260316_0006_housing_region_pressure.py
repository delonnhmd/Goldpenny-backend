"""housing region pressure mvp tables

Revision ID: 20260316_0006_housing_region
Revises: 20260316_0005_business_ops
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260316_0006_housing_region"
down_revision: Union[str, Sequence[str], None] = "20260316_0005_business_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "player_housing_states"):
        op.create_table(
            "player_housing_states",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("region", sa.String(length=40), nullable=False),
            sa.Column("housing_type", sa.String(length=40), nullable=False, server_default="starter_rent"),
            sa.Column("daily_housing_cost_xgp", sa.Numeric(14, 2), nullable=False),
            sa.Column("commute_modifier", sa.Numeric(8, 4), nullable=False, server_default="1.0"),
            sa.Column("stress_modifier", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("opportunity_modifier", sa.Numeric(8, 4), nullable=False, server_default="1.0"),
            sa.Column("active_flag", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_player_housing_states_player_id", "player_housing_states", ["player_id"], unique=False)
        op.create_index("ix_player_housing_states_region", "player_housing_states", ["region"], unique=False)
        op.create_index("ix_player_housing_states_active_flag", "player_housing_states", ["active_flag"], unique=False)

    if not _table_exists(bind, "housing_daily_logs"):
        op.create_table(
            "housing_daily_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("region", sa.String(length=40), nullable=False),
            sa.Column("housing_cost_xgp", sa.Numeric(14, 2), nullable=False),
            sa.Column("commute_pressure", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("stress_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("opportunity_modifier", sa.Numeric(8, 4), nullable=False, server_default="1.0"),
            sa.Column("notes_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("player_id", "day", name="uq_housing_daily_log_player_day"),
        )
        op.create_index("ix_housing_daily_logs_player_id", "housing_daily_logs", ["player_id"], unique=False)
        op.create_index("ix_housing_daily_logs_day", "housing_daily_logs", ["day"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "housing_daily_logs"):
        op.drop_index("ix_housing_daily_logs_day", table_name="housing_daily_logs")
        op.drop_index("ix_housing_daily_logs_player_id", table_name="housing_daily_logs")
        op.drop_table("housing_daily_logs")

    if _table_exists(bind, "player_housing_states"):
        op.drop_index("ix_player_housing_states_active_flag", table_name="player_housing_states")
        op.drop_index("ix_player_housing_states_region", table_name="player_housing_states")
        op.drop_index("ix_player_housing_states_player_id", table_name="player_housing_states")
        op.drop_table("player_housing_states")
