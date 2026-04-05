"""make_report_nullable_fields

Revision ID: f3a9b2c1d4e5
Revises: 1973215b1c0c
Create Date: 2026-03-15 15:00:00.000000

Make reports.uploaded_by and reports.organization_id nullable so that
patients can self-upload reports without needing a user account or org link.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "f3a9b2c1d4e5"
down_revision: Union[str, None] = "1973215b1c0c"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "reports",
        "uploaded_by",
        existing_type=UUID(),
        nullable=True,
    )
    op.alter_column(
        "reports",
        "organization_id",
        existing_type=UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "reports",
        "organization_id",
        existing_type=UUID(),
        nullable=False,
    )
    op.alter_column(
        "reports",
        "uploaded_by",
        existing_type=UUID(),
        nullable=False,
    )
