"""add gender to players.

Revision ID: 20260317_0011_player_gender
Revises: 20260317_0010_daily_brief
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260317_0011_player_gender"
down_revision: Union[str, Sequence[str], None] = "20260317_0010_daily_brief"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("gender", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "gender")
