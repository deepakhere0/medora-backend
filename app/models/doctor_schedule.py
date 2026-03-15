"""
DoctorSchedule defines a doctor's weekly availability pattern.
Each row represents one day of the week the doctor works,
with start/end times and optional lunch break.
Slot times are derived at query time from start_time, end_time,
and slot_duration_minutes (break period excluded).

Example: day_of_week=0 (Monday), start=09:00, end=17:00,
slot_duration_minutes=30, break_start=13:00, break_end=14:00
→ slots: 09:00, 09:30, ..., 12:30, 14:00, 14:30, ..., 16:30
"""

import uuid
from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctor_schedules"

    __table_args__ = (
        UniqueConstraint("doctor_id", "day_of_week", name="uq_doctor_schedule_day"),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # 0=Monday, 1=Tuesday, ..., 6=Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="schedules")
    organization: Mapped["Organization"] = relationship("Organization", back_populates="doctor_schedules")
