import enum
import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field, field_validator
from pydantic import BaseModel
from typing import Annotated


class DoctorGender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class DoctorEmploymentType(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    visiting = "visiting"


class DoctorStatus(str, enum.Enum):
    active = "active"
    on_duty = "on_duty"
    on_call = "on_call"
    on_leave = "on_leave"
    inactive = "inactive"


class DoctorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]
    gender: DoctorGender
    specialization: Annotated[str, Field(min_length=2, max_length=100)]
    experience_years: Annotated[int, Field(ge=0, le=60)]
    education: str | None = None
    license_number: Annotated[str, Field(min_length=3, max_length=100)]
    license_expiry: date
    employment_type: DoctorEmploymentType
    certifications: list[str] | None = None
    phone: str | None = None
    email: EmailStr | None = None
    photo_url: str | None = None
    staff_record: str | None = None
    medical_council: str | None = None
    registration_year: int | None = None
    registration_certificate_url: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip().lower()

    @field_validator("license_expiry")
    @classmethod
    def expiry_must_be_future(cls, v: date) -> date:
        if v <= date.today():
            raise ValueError("License expiry must be a future date")
        return v


class DoctorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    gender: DoctorGender | None = None
    specialization: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    experience_years: Annotated[int, Field(ge=0, le=60)] | None = None
    education: str | None = None
    license_number: Annotated[str, Field(min_length=3, max_length=100)] | None = None
    license_expiry: date | None = None
    employment_type: DoctorEmploymentType | None = None
    certifications: list[str] | None = None
    phone: str | None = None
    email: EmailStr | None = None
    photo_url: str | None = None
    staff_record: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip().lower()

    @field_validator("license_expiry")
    @classmethod
    def expiry_must_be_future(cls, v: date | None) -> date | None:
        if v is None:
            return v
        if v <= date.today():
            raise ValueError("License expiry must be a future date")
        return v


class DoctorStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DoctorStatus


class DoctorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    organization_id: UUID | None
    name: str
    gender: DoctorGender
    specialization: str
    experience_years: int
    education: str | None
    license_number: str
    license_expiry: date
    employment_type: DoctorEmploymentType
    certifications: list[str] | None
    phone: str | None
    email: str | None
    photo_url: str | None
    staff_record: str | None
    medical_council: str | None
    registration_year: int | None
    registration_certificate_url: str | None
    status: DoctorStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DoctorListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    name: str
    specialization: str
    phone: str | None
    status: DoctorStatus
    photo_url: str | None
    experience_years: int
    employment_type: DoctorEmploymentType


class DoctorStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_doctors: int
    on_duty_count: int
    on_leave_count: int
    new_this_week: int


# ---------------------------------------------------------------------------
# Doctor self-registration / auth schemas
# ---------------------------------------------------------------------------

class DoctorRegisterRequest(BaseModel):
    """Payload for POST /api/v1/doctor/register"""

    # User account fields
    name: Annotated[str, Field(min_length=2, max_length=255)]
    email: EmailStr
    phone: str
    password: str

    # Professional identity
    nmc_registration_number: Annotated[str, Field(min_length=3, max_length=100)]
    specialty: Annotated[str, Field(min_length=2, max_length=100)]
    degree: str | None = None
    experience_years: Annotated[int, Field(ge=0, le=60)]
    gender: DoctorGender

    # Fees & availability
    consultation_fee: Annotated[Decimal, Field(ge=0, decimal_places=2)] = Decimal("0")
    online_consultation_fee: Annotated[Decimal, Field(ge=0, decimal_places=2)] = Decimal("0")
    is_available_online: bool = False

    # Profile / discovery
    languages_spoken: str | None = None
    about_text: str | None = None

    # Location (for independent clinic)
    address: str | None = None
    pincode: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        digits = re.sub(r"[\s\-\(\)]", "", v)
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return digits

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class DoctorRegisterResponse(BaseModel):
    message: str
    doctor_id: UUID
    user_id: UUID


class DoctorLoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class DoctorProfileResponse(BaseModel):
    """Full profile returned to an authenticated doctor (GET /me, login response)."""
    model_config = ConfigDict(from_attributes=True)

    # From users table
    user_id: UUID
    name: str
    email: str
    phone: str | None

    # Core doctor identity
    doctor_id: UUID
    nmc_registration_number: str | None
    specialty: str | None
    specialization: str
    degree: str | None
    experience_years: int
    gender: str

    # Fees & availability
    consultation_fee: Decimal
    online_consultation_fee: Decimal
    is_available_online: bool

    # Profile
    languages_spoken: str | None
    about_text: str | None
    profile_photo_url: str | None
    registration_certificate_url: str | None

    # Location
    address: str | None
    pincode: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None

    # Stats & status
    average_rating: Decimal
    total_reviews: int
    is_independent: bool
    is_verified: bool
    self_registered: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DoctorLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    doctor: DoctorProfileResponse


class DoctorPublicProfile(BaseModel):
    """What patients see — no PII (email/phone hidden), shows rating."""
    model_config = ConfigDict(from_attributes=True)

    doctor_id: UUID
    name: str
    specialty: str | None
    specialization: str
    degree: str | None
    experience_years: int
    gender: str
    consultation_fee: Decimal
    online_consultation_fee: Decimal
    is_available_online: bool
    languages_spoken: str | None
    about_text: str | None
    profile_photo_url: str | None
    address: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    average_rating: Decimal
    total_reviews: int


# ---------------------------------------------------------------------------
# Public search / discovery schemas
# ---------------------------------------------------------------------------

class DoctorSearchItem(BaseModel):
    """One doctor in a search result page."""
    doctor_id: UUID
    name: str
    specialty: str | None
    specialization: str
    degree: str | None
    experience_years: int
    consultation_fee: Decimal
    online_consultation_fee: Decimal
    is_available_online: bool
    average_rating: Decimal
    total_reviews: int
    profile_photo_url: str | None
    city: str | None
    state: str | None
    languages_spoken: str | None
    gender: str
    distance_km: float | None = None  # only present when lat/lng provided


class DoctorSearchResponse(BaseModel):
    doctors: list[DoctorSearchItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class ReviewItem(BaseModel):
    id: UUID
    patient_first_name: str
    rating: int
    review_text: str | None
    created_at: datetime
    is_verified: bool


class ReviewsResponse(BaseModel):
    reviews: list[ReviewItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class CreateReviewRequest(BaseModel):
    appointment_id: UUID
    rating: Annotated[int, Field(ge=1, le=5)]
    review_text: str | None = None


class CreateReviewResponse(BaseModel):
    id: UUID
    doctor_id: UUID
    rating: int
    review_text: str | None
    is_verified: bool
    created_at: datetime
    message: str


class PublicDoctorProfileResponse(BaseModel):
    """
    Full public profile including recent reviews and next-7-day slot availability.
    Email and phone are never included.
    """
    doctor_id: UUID
    name: str
    specialty: str | None
    specialization: str
    degree: str | None
    experience_years: int
    gender: str
    consultation_fee: Decimal
    online_consultation_fee: Decimal
    is_available_online: bool
    languages_spoken: str | None
    about_text: str | None
    profile_photo_url: str | None
    registration_certificate_url: str | None
    address: str | None
    pincode: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    average_rating: Decimal
    total_reviews: int
    recent_reviews: list[ReviewItem]
    # Keys are ISO date strings ("2026-04-15"), values are HH:MM slot strings
    available_slots: dict[str, list[str]]


class SpecialtiesResponse(BaseModel):
    specialties: list[str]
