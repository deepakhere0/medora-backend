"""add org settings columns

Revision ID: b1e2f3a4c5d6
Revises: c673c1a76aa8
Create Date: 2026-04-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'b1e2f3a4c5d6'
down_revision: Union[str, None] = 'c673c1a76aa8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('pincode', sa.String(10), nullable=True))
    op.add_column('organizations', sa.Column('description', sa.String(2000), nullable=True))
    op.add_column('organizations', sa.Column('operating_hours', JSONB(), nullable=True))
    op.add_column('organizations', sa.Column('departments', JSONB(), nullable=True, server_default='[]'))


def downgrade() -> None:
    op.drop_column('organizations', 'departments')
    op.drop_column('organizations', 'operating_hours')
    op.drop_column('organizations', 'description')
    op.drop_column('organizations', 'pincode')
