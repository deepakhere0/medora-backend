"""change certificate url to text

Revision ID: a9b8c7d6e5f4
Revises: f6e5d4c3b2a1
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'f6e5d4c3b2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'organizations',
        'registration_certificate_url',
        type_=sa.Text(),
        existing_type=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'organizations',
        'registration_certificate_url',
        type_=sa.String(500),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
