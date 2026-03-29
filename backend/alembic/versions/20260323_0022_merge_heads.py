"""merge_heads

Revision ID: 20260323_0022_merge_heads
Revises: 20260323_0021_soft_launch, 85854026afad
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260323_0022_merge_heads'
down_revision: Union[str, Sequence[str], None] = ('20260323_0021_soft_launch', '85854026afad')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge branches — no schema changes needed."""
    pass


def downgrade() -> None:
    """Merge branches — no schema changes needed."""
    pass
