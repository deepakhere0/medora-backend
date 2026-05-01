"""
Pydantic v2 schemas for the authenticated doctor dashboard.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Annotated


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

class WeeklySlotSummary(BaseModel):
    date: date
    day_name: str
    open_slots_count: int


class UpcomingAppointmentBrief(BaseModel):
    id: UUID
    patient_name: str
    appointment_date: date
    start_time: str
    end_time: str
    type: str        # "in_clinic" | "video"
    status: str
    consultation_fee: Decimal


class DashboardReviewItem(BaseModel):
    id: UUID
    patient_first_name: str
    rating: int
    review_text: str | None
    created_at: datetime


class DoctorDashboardResponse(BaseModel):
    today_appointments: int
    today_online_consults: int
    this_month_earnings: Decimal
    last_month_earnings: Decimal
    earnings_comparison_pct: float
    rating: Decimal
    total_reviews: int
    upcoming_appointments: list[UpcomingAppointmentBrief]
    weekly_slots: list[WeeklySlotSummary]
    recent_reviews: list[DashboardReviewItem]


# ---------------------------------------------------------------------------
# Appointments list
# ---------------------------------------------------------------------------

class DoctorAppointmentItem(BaseModel):
    id: UUID
    patient_name: str
    patient_phone: str | None
    appointment_date: date
    start_time: str
    end_time: str
    type: str         # "in_clinic" | "video"
    status: str
    consultation_fee: Decimal
    booking_id: str | None
    notes: str | None


class DoctorAppointmentsResponse(BaseModel):
    appointments: list[DoctorAppointmentItem]
    total: int
    page: int
    per_page: int
    total_pages: int


# ---------------------------------------------------------------------------
# Profile update
# ---------------------------------------------------------------------------

class DoctorProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specialty: str | None = None
    degree: str | None = None
    experience_years: Annotated[int, Field(ge=0, le=60)] | None = None
    consultation_fee: Annotated[Decimal, Field(ge=0)] | None = None
    online_consultation_fee: Annotated[Decimal, Field(ge=0)] | None = None
    is_available_online: bool | None = None
    languages_spoken: str | None = None
    about_text: str | None = None
    gender: str | None = None
    address: str | None = None
    pincode: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in ("male", "female", "other"):
            raise ValueError("gender must be 'male', 'female', or 'other'")
        return v


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

class ScheduleEntryResponse(BaseModel):
    """One day's schedule as returned by GET /schedule."""
    id: UUID
    day_of_week: int
    day_name: str
    start_time: str     # "HH:MM"
    end_time: str
    slot_duration_minutes: int
    break_start: str | None
    break_end: str | None
    is_active: bool


class ScheduleResponse(BaseModel):
    schedules: list[ScheduleEntryResponse]


class ScheduleEntryInput(BaseModel):
    """One day's schedule as submitted by PUT /schedule."""
    day_of_week: Annotated[int, Field(ge=0, le=6)]
    start_time: str    # "HH:MM"
    end_time: str
    slot_duration_minutes: Annotated[int, Field(ge=5, le=120)] = 30
    break_start: str | None = None
    break_end: str | None = None
    is_active: bool = True

    @field_validator("start_time", "end_time", "break_start", "break_end")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        h, m = parts
        if not (h.isdigit() and m.isdigit()):
            raise ValueError("Time must be in HH:MM format")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError("Invalid time value")
        return v


class UpdateScheduleRequest(BaseModel):
    schedules: list[ScheduleEntryInput]

    @field_validator("schedules")
    @classmethod
    def no_duplicate_days(cls, v: list[ScheduleEntryInput]) -> list[ScheduleEntryInput]:
        days = [e.day_of_week for e in v]
        if len(days) != len(set(days)):
            raise ValueError("Duplicate day_of_week entries — each weekday may appear at most once")
        return v


# ---------------------------------------------------------------------------
# Earnings
# ---------------------------------------------------------------------------

class DailyEarning(BaseModel):
    date: date
    amount: Decimal
    count: int


class EarningsBreakdown(BaseModel):
    in_clinic: Decimal
    online: Decimal


class EarningsResponse(BaseModel):
    period_label: str
    total_earnings: Decimal
    breakdown: EarningsBreakdown
    daily_earnings: list[DailyEarning]
    comparison_percentage: float   # vs previous same-length period; positive = growth


# ---------------------------------------------------------------------------
# My reviews (doctor sees their own)
# ---------------------------------------------------------------------------

class DoctorReviewItem(BaseModel):
    id: UUID
    patient_first_name: str
    rating: int
    review_text: str | None
    appointment_date: date | None
    created_at: datetime
    is_verified: bool


class DoctorReviewsResponse(BaseModel):
    reviews: list[DoctorReviewItem]
    total: int
    page: int
    per_page: int
    total_pages: int


# ---------------------------------------------------------------------------
# My patients
# ---------------------------------------------------------------------------

class DoctorPatientItem(BaseModel):
    patient_id: UUID
    patient_name: str
    patient_phone: str | None
    last_visit_date: date | None
    total_visits: int


class DoctorPatientsResponse(BaseModel):
    patients: list[DoctorPatientItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class DoctorPatientReportItem(BaseModel):
    id: UUID
    title: str | None
    upload_type: str | None
    file_url: str | None
    file_type: str | None
    ai_analysis: str | None
    ai_analysis_status: str | None
    is_report_analysis: bool
    created_at: datetime


class DoctorPatientDetailResponse(BaseModel):
    patient_id: UUID
    patient_name: str
    patient_phone: str | None
    date_of_birth: date | None
    gender: str | None
    blood_group: str | None
    allergies: str | None
    avatar_url: str | None
    last_visit_date: date | None
    total_visits: int
    reports: list[DoctorPatientReportItem]
    appointments: list[DoctorAppointmentItem]


# ---------------------------------------------------------------------------
# Consultation Notes
# ---------------------------------------------------------------------------

class UpsertConsultationNoteRequest(BaseModel):
    """Body for POST /doctor/notes — creates or replaces the note for a (doctor, patient) pair."""
    patient_id: UUID
    content: str = Field(default="", max_length=10_000)
    client_updated_at: datetime | None = None
    version: int | None = None


class ConsultationNoteResponse(BaseModel):
    id: UUID
    doctor_id: UUID
    patient_id: UUID
    content: str
    version: int
    created_at: datetime
    updated_at: datetime

class AuditLogResponse(BaseModel):
    id: UUID
    doctor_id: UUID
    patient_id: UUID
    appointment_id: UUID | None
    action: str
    created_at: datetime
