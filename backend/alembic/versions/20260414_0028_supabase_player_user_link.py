"""Step 95E: link players.user_id to Supabase Auth (text, nullable, unique).

Revision ID: 20260414_0028_supabase_player_user_link
Revises: 20260414_0027_auth_account_foundation
Create Date: 2026-04-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260414_0028_supabase_player_user_link"
down_revision: Union[str, Sequence[str], None] = "20260414_0027_auth_account_foundation"
branch_labels = None
depends_on = None


def _drop_constraint_if_exists(table: str, name: str, type_: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if type_ == "foreignkey":
        existing = {fk.get("name") for fk in inspector.get_foreign_keys(table)}
    elif type_ == "unique":
        existing = {uq.get("name") for uq in inspector.get_unique_constraints(table)}
    else:
        existing = set()
    if name in existing:
        op.drop_constraint(name, table, type_=type_)


def upgrade() -> None:
    # Drop the FK to the legacy users table — Supabase auth user ids are not
    # tracked in this database.
    _drop_constraint_if_exists("players", "players_user_id_fkey", "foreignkey")
    _drop_constraint_if_exists("players", "fk_players_user_id_users", "foreignkey")

    # Drop the existing unique constraint so we can swap in a partial unique
    # index that allows multiple NULLs.
    _drop_constraint_if_exists("players", "uq_players_user_id", "unique")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {ix["name"] for ix in inspector.get_indexes("players")}
    if "ix_players_user_id" in indexes:
        op.drop_index("ix_players_user_id", table_name="players")

    # Convert UUID -> TEXT and allow NULL.
    op.alter_column(
        "players",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        type_=sa.Text(),
        existing_nullable=False,
        nullable=True,
        postgresql_using="user_id::text",
    )

    op.create_index(
        "ux_players_user_id",
        "players",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {ix["name"] for ix in inspector.get_indexes("players")}
    if "ux_players_user_id" in indexes:
        op.drop_index("ux_players_user_id", table_name="players")

    op.alter_column(
        "players",
        "user_id",
        existing_type=sa.Text(),
        type_=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        nullable=False,
        postgresql_using="user_id::uuid",
    )
    op.create_index("ix_players_user_id", "players", ["user_id"], unique=True)
    op.create_unique_constraint("uq_players_user_id", "players", ["user_id"])
