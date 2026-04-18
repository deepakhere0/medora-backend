import enum
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from typing import Annotated, Optional

from app.schemas.patient import PatientGender, PatientBloodType


class AppointmentStatus(str, enum.Enum):
    pending = "pending"
    scheduled = "scheduled"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    rejected = "rejected"


class AppointmentType(str, enum.Enum):
    walk_in = "walk_in"
    scheduled = "scheduled"


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: UUID
    patient_id: UUID
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: AppointmentType = AppointmentType.scheduled
    notes: str | None = None

    @field_validator("appointment_date")
    @classmethod
    def date_not_in_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("Appointment date cannot be in the past")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "AppointmentCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AppointmentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AppointmentStatus
    cancellation_reason: str | None = None

    @model_validator(mode="after")
    def require_reason_when_cancelling(self) -> "AppointmentStatusUpdate":
        if self.status == AppointmentStatus.cancelled and self.cancellation_reason is None:
            raise ValueError("cancellation_reason is required when cancelling")
        return self


class AppointmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> "AppointmentUpdate":
        if self.start_time is not None and self.end_time is not None:
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be after start_time")
        return self


def _calc_duration(start: time, end: time) -> int:
    s = datetime.combine(date.today(), start)
    e = datetime.combine(date.today(), end)
    return int((e - s).total_seconds() // 60)


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    doctor_id: UUID
    patient_id: UUID
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: AppointmentType
    status: AppointmentStatus
    notes: str | None
    cancellation_reason: str | None
    token_number: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def duration_minutes(self) -> int:
        return _calc_duration(self.start_time, self.end_time)


class AppointmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    patient_id: UUID
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: AppointmentType
    status: AppointmentStatus
    token_number: int | None
    booking_for: str | None = None
    guest_name: str | None = None
    # Patient info
    patient_name: str | None = None
    patient_phone: str | None = None
    patient_code: str | None = None
    # Doctor info
    doctor_name: str | None = None
    doctor_specialization: str | None = None
    created_at: datetime

    @computed_field
    @property
    def duration_minutes(self) -> int:
        return _calc_duration(self.start_time, self.end_time)


class AppointmentListResponse(BaseModel):
    appointments: list[AppointmentListItem]
    total: int
    page: int
    limit: int


class AppointmentStatsResponse(BaseModel):
    total_today: int
    scheduled_count: int
    confirmed_count: int
    in_progress_count: int
    completed_count: int
    cancelled_count: int


class AppointmentCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    note: Optional[str] = None


class AppointmentRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = None


class WalkInAppointmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Patient fields
    patient_name:          Annotated[str, Field(min_length=1, max_length=255)]
    patient_gender:        PatientGender
    patient_phone:         Annotated[str, Field(min_length=5, max_length=20)]
    patient_email:         str | None = None
    patient_date_of_birth: date | None = None
    patient_address:       str | None = None
    patient_blood_type:    PatientBloodType | None = None

    # Appointment fields
    doctor_id:        UUID
    appointment_date: date
    start_time:       time
    end_time:         time
    notes:            str | None = None

    @field_validator("patient_name", mode="before")
    @classmethod
    def strip_patient_name(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("patient_name must not be empty")
        return v

    @field_validator("appointment_date")
    @classmethod
    def date_not_in_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("appointment_date cannot be in the past")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "WalkInAppointmentRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class WalkInAppointmentResponse(BaseModel):
    appointment_id:   UUID
    booking_id:       str | None
    patient_id:       UUID
    patient_code:     str
    patient_name:     str
    doctor_name:      str
    appointment_date: date
    start_time:       str
    end_time:         str
    status:           str
    message:          str
