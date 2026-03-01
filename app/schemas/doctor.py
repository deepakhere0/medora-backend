import enum
from datetime import date, datetime
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
    organization_id: UUID
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
