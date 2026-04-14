"""Step 95: auth account foundation metadata.

Revision ID: 20260414_0027_auth_account_foundation
Revises: 20260407_0026_player_job_progression_tracks
Create Date: 2026-04-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260414_0027_auth_account_foundation"
down_revision: Union[str, Sequence[str], None] = "20260407_0026_player_job_progression_tracks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'password'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.execute(
        """
        UPDATE users
        SET password_updated_at = COALESCE(password_updated_at, created_at, CURRENT_TIMESTAMP)
        """
    )


def downgrade() -> None:
    op.drop_column("users", "password_updated_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "status")
    op.drop_column("users", "auth_provider")
