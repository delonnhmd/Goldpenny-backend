"""Step 43 — Supply Chain Graph + Node State tables.

Revision ID:  20260321_0019_supply_chain_graph
Revises:      20260321_0018_forecasting_planning
Create Date:  2026-03-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260321_0019_supply_chain_graph"
down_revision = "20260321_0018_forecasting_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── supply_chain_node_states ─────────────────────────────────────────────
    op.create_table(
        "supply_chain_node_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_key", sa.String(40), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Numeric(8, 4), nullable=False, server_default="1.0000"),
        sa.Column("required", sa.Numeric(8, 4), nullable=False, server_default="1.0000"),
        sa.Column("reliability", sa.Numeric(8, 4), nullable=False, server_default="1.0000"),
        sa.Column("unit_cost_override", sa.Numeric(14, 4), nullable=True),
        sa.Column("region_modifier_suburban", sa.Numeric(8, 4), nullable=False, server_default="1.0000"),
        sa.Column("region_modifier_downtown", sa.Numeric(8, 4), nullable=False, server_default="1.0000"),
        sa.Column("region_modifier_rural", sa.Numeric(8, 4), nullable=False, server_default="1.0000"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_updated_on", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_key", "day", name="uq_scns_node_day"),
    )
    op.create_index("ix_scns_node_key", "supply_chain_node_states", ["node_key"])
    op.create_index("ix_scns_day", "supply_chain_node_states", ["day"])

    # ── supply_chain_daily_snapshots ─────────────────────────────────────────
    op.create_table(
        "supply_chain_daily_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("top_bottleneck_node", sa.String(40), nullable=True),
        sa.Column("most_affected_basket", sa.String(30), nullable=True),
        sa.Column("best_job_opportunity", sa.String(40), nullable=True),
        sa.Column("overall_stress_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("node_states_json", sa.Text(), nullable=True),
        sa.Column("basket_multipliers_json", sa.Text(), nullable=True),
        sa.Column("bottlenecks_json", sa.Text(), nullable=True),
        sa.Column("job_pressure_json", sa.Text(), nullable=True),
        sa.Column("story_json", sa.Text(), nullable=True),
        sa.Column("debug_json", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", name="uq_scds_day"),
    )
    op.create_index("ix_scds_day", "supply_chain_daily_snapshots", ["day"])


def downgrade() -> None:
    op.drop_index("ix_scds_day", table_name="supply_chain_daily_snapshots")
    op.drop_table("supply_chain_daily_snapshots")

    op.drop_index("ix_scns_day", table_name="supply_chain_node_states")
    op.drop_index("ix_scns_node_key", table_name="supply_chain_node_states")
    op.drop_table("supply_chain_node_states")
