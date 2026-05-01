"""merge heads

Revision ID: 9a410ffb6004
Revises: 2026_05_01_add_audit_log, a1b2c3d4e5f6
Create Date: 2026-05-01 06:04:32.077294

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9a410ffb6004'
down_revision: Union[str, None] = ('2026_05_01_add_audit_log', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
