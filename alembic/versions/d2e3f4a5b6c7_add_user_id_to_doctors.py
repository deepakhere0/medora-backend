"""add user_id to doctors for self-registered doctor accounts

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-04-14 00:00:00.000000

Independent/self-registered doctors have a User account (role='doctor').
This FK links the two records so we can look up a doctor's profile from
their JWT sub (user_id).

  - NULL for hospital-affiliated doctors created by org_admin (no user account)
  - Set once at self-registration, never changes after that
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doctors",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_doctors_user_id", "doctors", ["user_id"])
    op.create_index("ix_doctors_user_id", "doctors", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_doctors_user_id", table_name="doctors")
    op.drop_constraint("uq_doctors_user_id", "doctors", type_="unique")
    op.drop_column("doctors", "user_id")
