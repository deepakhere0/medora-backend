from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Step 1-2: Location
# ---------------------------------------------------------------------------

class StateResponse(BaseModel):
    state: str
    hospital_count: int


class CityResponse(BaseModel):
    city: str
    hospital_count: int


# ---------------------------------------------------------------------------
# Step 3: Hospital selection
# ---------------------------------------------------------------------------

class HospitalBrief(BaseModel):
    id: UUID
    name: str
    city: str
    state: str
    address: str | None
    logo_url: str | None
    doctor_count: int
    available_slots_today: int


# ---------------------------------------------------------------------------
# Step 4: Doctor selection
# ---------------------------------------------------------------------------

class DoctorBrief(BaseModel):
    id: UUID
    name: str
    specialization: str
    experience_years: int
    photo_url: str | None
    gender: str
    status: str


class SpecializationResponse(BaseModel):
    specialization: str
    doctor_count: int


# ---------------------------------------------------------------------------
# Step 5: Slot selection
# ---------------------------------------------------------------------------

class AvailableSlot(BaseModel):
    start_time: str   # "09:00"
    end_time: str     # "09:30"
    is_available: bool


class DaySlotsResponse(BaseModel):
    date: date
    day_name: str               # "Monday"
    morning: list[AvailableSlot]    # before 12:00
    afternoon: list[AvailableSlot]  # 12:00–17:00
    evening: list[AvailableSlot]    # 17:00 and after


class WeekSlotsResponse(BaseModel):
    doctor_id: UUID
    doctor_name: str
    schedule_exists: bool
    week_start: date
    days: list[DaySlotsResponse]


# ---------------------------------------------------------------------------
# Step 6: Create appointment
# ---------------------------------------------------------------------------

class BookAppointmentRequest(BaseModel):
    organization_id: UUID
    doctor_id: UUID
    appointment_date: date
    start_time: str       # "10:30"
    notes: str | None = None
    booking_for: str = "self"        # "self" or "someone_else"
    guest_name: str | None = None
    guest_age: int | None = None
    guest_sex: str | None = None
    guest_phone: str | None = None
    guest_email: str | None = None


class BookAppointmentResponse(BaseModel):
    id: UUID
    booking_id: str
    organization_name: str
    hospital_address: str | None
    hospital_city: str
    hospital_state: str
    doctor_name: str
    doctor_specialization: str
    appointment_date: date
    start_time: str
    end_time: str
    status: str
    created_at: datetime
    booking_for: str
    guest_name: str | None = None
    guest_age: int | None = None
    guest_sex: str | None = None
    guest_phone: str | None = None
    guest_email: str | None = None
