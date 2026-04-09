"""add hospital verification fields

Revision ID: f6e5d4c3b2a1
Revises: b1e2f3a4c5d6
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6e5d4c3b2a1'
down_revision: Union[str, None] = 'b1e2f3a4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('registration_number', sa.String(100), nullable=True))
    op.add_column('organizations', sa.Column('registration_certificate_url', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'registration_certificate_url')
    op.drop_column('organizations', 'registration_number')
