"""
OnlineConsultation tracks a video/audio/chat session between a doctor and a patient.

Lifecycle:  scheduled → in_progress → completed | cancelled | no_show
Payment:    pending → paid | refunded

meeting_room_id stores the room/session token for the video call provider
(e.g. Daily.co room name, Agora channel ID, or Whereby meeting URL).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class OnlineConsultation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "online_consultations"

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
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 'video' | 'audio' | 'chat'
    consultation_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="video", server_default="'video'"
    )
    # 'scheduled' | 'in_progress' | 'completed' | 'cancelled' | 'no_show'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled", server_default="'scheduled'"
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    meeting_room_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prescription_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    consultation_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    # 'pending' | 'paid' | 'refunded'
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="'pending'"
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    doctor = relationship("Doctor", back_populates="online_consultations", lazy="noload")
    patient = relationship("Patient", back_populates="online_consultations", lazy="noload")
    appointment = relationship("Appointment", back_populates="online_consultations", lazy="noload")
