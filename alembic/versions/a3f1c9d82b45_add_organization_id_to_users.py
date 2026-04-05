"""add organization_id to users

Revision ID: a3f1c9d82b45
Revises: 1591a872ed02
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f1c9d82b45"
down_revision: Union[str, None] = "1591a872ed02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_users_organization_id"),
        "users",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_column("users", "organization_id")
