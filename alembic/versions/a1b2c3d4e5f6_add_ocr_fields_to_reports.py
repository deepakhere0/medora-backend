"""add_ocr_fields_to_reports

Revision ID: a1b2c3d4e5f6
Revises: 256d54fca8a4
Create Date: 2026-04-29 14:00:00.000000

Add OCR pipeline columns to the reports table:
  - extracted_text : raw text returned by Google Cloud Vision API
  - clean_text     : normalised / cleaned version of extracted_text

Both columns are nullable TEXT — existing rows will have NULL, which is the
correct default (no OCR has been run on legacy reports).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "256d54fca8a4"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("extracted_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column("clean_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "clean_text")
    op.drop_column("reports", "extracted_text")
