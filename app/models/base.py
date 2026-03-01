"""
app/models/base.py

Foundational building blocks for all MEDORA models.

Provides:
- Base          : SQLAlchemy DeclarativeBase root (no table)
- UUIDPrimaryKeyMixin : UUID primary key for every entity
- TimestampMixin      : Audit timestamps (created_at / updated_at)
- TenantMixin         : Multi-tenant isolation via organization_id FK
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UUIDPrimaryKeyMixin:
    """Provides a UUID primary key column for any model."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """
    Automatically tracks row creation and last-update time.
    All timestamps are timezone-aware and set server-side.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """
    Enforces multi-tenant data isolation.
    Every tenant-scoped model must inherit this mixin so that rows
    are always bound to an organization. Cascade deletes ensure no
    orphaned records survive organization removal.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
