"""
Junction table linking patients to organizations.
Supports future many-to-many: a patient may belong to multiple organizations.
"""

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PatientOrganization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_organizations"

    __table_args__ = (
        UniqueConstraint("patient_id", "organization_id", name="uq_patient_org"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    registered_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    patient = relationship("Patient", back_populates="patient_organizations")
    organization = relationship("Organization", lazy="noload")
