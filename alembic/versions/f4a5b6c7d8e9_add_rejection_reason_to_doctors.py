"""Add rejection_reason column to doctors for admin doctor verification workflow

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-04-14 00:00:00.000000

Distinguishes "pending" (is_verified=False, rejection_reason IS NULL)
from "rejected" (is_verified=False, rejection_reason IS NOT NULL) without
adding a separate status enum.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doctors",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("doctors", "rejection_reason")
