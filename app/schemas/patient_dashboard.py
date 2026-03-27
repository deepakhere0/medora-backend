from datetime import date, time
from uuid import UUID

from pydantic import BaseModel


class PatientOrgBrief(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str


class PatientProfile(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    name: str
    email: str | None
    phone: str
    patient_code: str
    date_of_birth: date | None
    gender: str | None
    blood_type: str | None
    height_cm: float | None
    weight_kg: float | None
    blood_pressure: str | None
    heart_rate: int | None = None
    photo_url: str | None
    organizations: list[PatientOrgBrief]


class PatientProfileUpdate(BaseModel):
    phone: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    blood_type: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    blood_pressure: str | None = None
    heart_rate: int | None = None


class PatientAppointmentBrief(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    doctor_name: str
    doctor_specialty: str | None
    doctor_photo_url: str | None
    organization_name: str
    hospital_address: str | None
    hospital_city: str | None
    hospital_state: str | None
    appointment_date: date
    start_time: time
    end_time: time | None
    status: str
    consultation_type: str | None
    notes: str | None


class PatientAppointmentsResponse(BaseModel):
    appointments: list[PatientAppointmentBrief]
    total: int


class PatientDashboardResponse(BaseModel):
    profile: PatientProfile
    upcoming_appointments: list[PatientAppointmentBrief]
    total_appointments: int
    total_reports: int
