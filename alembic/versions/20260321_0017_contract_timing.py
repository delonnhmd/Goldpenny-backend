"""Step 41 — Contracts, recurring obligations, and calendar pressure layer.

Revision ID:  20260321_0017_contract_timing
Revises:      20260321_0016_reputation_trust
Create Date:  2026-03-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260321_0017_contract_timing"
down_revision = "20260321_0016_reputation_trust"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # player_contract_schedules  (one rolling row per player)
    # ------------------------------------------------------------------
    op.create_table(
        "player_contract_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_contract_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_due_7d_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("clustering_label", sa.String(30), nullable=False, server_default="spread"),
        sa.Column("next_major_due_on", sa.Integer(), nullable=True),
        sa.Column("next_major_due_type", sa.String(60), nullable=True),
        sa.Column("days_to_next_major_due", sa.Integer(), nullable=True),
        sa.Column("next_income_on", sa.Integer(), nullable=True),
        sa.Column("next_income_type", sa.String(40), nullable=True),
        sa.Column("days_to_next_income", sa.Integer(), nullable=True),
        sa.Column("contract_density_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("timing_stability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("cash_gap_before_next_income_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("timing_pressure_label", sa.String(30), nullable=False, server_default="manageable"),
        sa.Column("bridge_need_label", sa.String(30), nullable=False, server_default="none"),
        sa.Column("obligation_collision_label", sa.String(30), nullable=False, server_default="none"),
        sa.Column("recurring_obligation_map_json", sa.Text(), nullable=True),
        sa.Column("income_cadence_json", sa.Text(), nullable=True),
        sa.Column("due_window_json", sa.Text(), nullable=True),
        sa.Column("debug_json", sa.Text(), nullable=True),
        sa.Column("false_payday_pressure", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_updated_on", sa.Integer(), nullable=True),
        sa.Column("last_updated_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", name="uq_pcs_player"),
    )
    op.create_index("ix_pcs_player_id", "player_contract_schedules", ["player_id"])

    # ------------------------------------------------------------------
    # player_contract_events  (bounded log of individual obligation instances)
    # ------------------------------------------------------------------
    op.create_table(
        "player_contract_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_key", sa.String(60), nullable=False),
        sa.Column("obligation_family", sa.String(40), nullable=False),
        sa.Column("obligation_type", sa.String(40), nullable=False),
        sa.Column("amount_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("cycle_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("due_on_day", sa.Integer(), nullable=False),
        sa.Column("due_on_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="upcoming"),
        sa.Column("income_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("paid_on_day", sa.Integer(), nullable=True),
        sa.Column("paid_amount_xgp", sa.Numeric(14, 4), nullable=True),
        sa.Column("resolution_note", sa.String(120), nullable=True),
        sa.Column("source_loan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("debug_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "player_id", "obligation_key", "due_on_day",
            name="uq_pce_player_obligation_day",
        ),
    )
    op.create_index("ix_pce_player_id", "player_contract_events", ["player_id"])
    op.create_index("ix_pce_due_on_day", "player_contract_events", ["due_on_day"])
    op.create_index("ix_pce_status", "player_contract_events", ["status"])
    op.create_index("ix_pce_player_due", "player_contract_events", ["player_id", "due_on_day"])


def downgrade() -> None:
    op.drop_index("ix_pce_player_due", table_name="player_contract_events")
    op.drop_index("ix_pce_status", table_name="player_contract_events")
    op.drop_index("ix_pce_due_on_day", table_name="player_contract_events")
    op.drop_index("ix_pce_player_id", table_name="player_contract_events")
    op.drop_table("player_contract_events")

    op.drop_index("ix_pcs_player_id", table_name="player_contract_schedules")
    op.drop_table("player_contract_schedules")
