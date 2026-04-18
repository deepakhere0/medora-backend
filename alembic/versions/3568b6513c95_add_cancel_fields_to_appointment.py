"""add cancel fields to appointment

Revision ID: 3568b6513c95
Revises: f4a5b6c7d8e9
Create Date: 2026-04-18 16:50:02.379919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3568b6513c95'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('appointments', sa.Column('cancel_note', sa.Text(), nullable=True))
    op.add_column('appointments', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('appointments', 'cancelled_at')
    op.drop_column('appointments', 'cancel_note')
