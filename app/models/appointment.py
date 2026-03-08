import enum
import uuid
from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import ENUM as PgENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AppointmentStatus(str, enum.Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class AppointmentType(str, enum.Enum):
    walk_in = "walk_in"
    scheduled = "scheduled"


appointment_status_enum = PgENUM(
    "scheduled",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    name="appointment_status",
    create_type=False,
)

appointment_type_enum = PgENUM(
    "walk_in",
    "scheduled",
    name="appointment_type",
    create_type=False,
)


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Central scheduling entity in MEDORA.
    Connects a patient to a doctor at a specific date and time,
    scoped to a tenant organization.
    """

    __tablename__ = "appointments"

    __table_args__ = (
        Index("ix_appt_org_date", "organization_id", "appointment_date"),
        Index("ix_appt_org_doctor_date", "organization_id", "doctor_id", "appointment_date"),
        Index("ix_appt_org_patient", "organization_id", "patient_id"),
        Index("ix_appt_org_status", "organization_id", "status"),
        {},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    appointment_type: Mapped[str] = mapped_column(
        appointment_type_enum,
        nullable=False,
        server_default="scheduled",
    )
    status: Mapped[str] = mapped_column(
        appointment_status_enum,
        nullable=False,
        server_default="scheduled",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="appointments", lazy="noload"
    )
    doctor: Mapped["Doctor"] = relationship(
        "Doctor", back_populates="appointments", lazy="noload"
    )
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="appointments", lazy="noload"
    )
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="appointment", lazy="noload"
    )
