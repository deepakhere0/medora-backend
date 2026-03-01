"""
Appointment is the central scheduling entity in MEDORA.
Every clinical interaction between a doctor and a patient is recorded
here, scoped to a tenant (organization). It drives scheduling,
analytics, billing triggers, and audit trails across the platform.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, TenantMixin, UUIDPrimaryKeyMixin


class AppointmentStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "appointments"

    __table_args__ = (
        Index("ix_appointments_organization_id_scheduled_at", "organization_id", "scheduled_at"),
        Index("ix_appointments_organization_id_status", "organization_id", "status"),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointmentstatus", create_type=True),
        nullable=False,
        default=AppointmentStatus.scheduled,
        index=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    doctor = relationship("Doctor", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
