from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class MedicalHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "medical_history"

    __table_args__ = (
        Index("ix_medical_history_org_patient", "organization_id", "patient_id"),
        Index("ix_medical_history_patient_date", "patient_id", "event_date"),
        {},
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recorded_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="medical_histories", lazy="noload"
    )
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="medical_histories", lazy="noload"
    )
    appointment: Mapped["Appointment"] = relationship(
        "Appointment", back_populates="medical_histories", lazy="noload"
    )
    recorder: Mapped["User"] = relationship(
        "User",
        back_populates="medical_histories",
        lazy="noload",
        foreign_keys="[MedicalHistory.recorded_by]",
    )
