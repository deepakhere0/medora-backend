"""
app/schemas/patient.py

Part 1: Enums + Input Schemas  (PatientCreate, PatientUpdate)
Part 2: Response Schemas       (PatientRead, PatientListItem,
                                PatientDemographicsResponse, PatientListResponse)
"""

import enum
import re
import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

# ---------------------------------------------------------------------------
# Module-level constant — compiled once, reused by both schemas
# ---------------------------------------------------------------------------
_BP_RE: re.Pattern[str] = re.compile(r"^\d+/\d+$")


# ---------------------------------------------------------------------------
# Enums — values must exactly match the patient_gender / patient_blood_type
# PostgreSQL ENUM types defined in app/models/patient.py
# ---------------------------------------------------------------------------

class PatientGender(str, enum.Enum):
    male   = "male"
    female = "female"
    other  = "other"


class PatientBloodType(str, enum.Enum):
    A_pos  = "A_pos"
    A_neg  = "A_neg"
    B_pos  = "B_pos"
    B_neg  = "B_neg"
    O_pos  = "O_pos"
    O_neg  = "O_neg"
    AB_pos = "AB_pos"
    AB_neg = "AB_neg"


# ---------------------------------------------------------------------------
# PatientCreate
# ---------------------------------------------------------------------------

class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:           Annotated[str, Field(min_length=1, max_length=255)]
    gender:         PatientGender
    date_of_birth:  date
    phone:          Annotated[str, Field(min_length=5, max_length=20)]
    email:          EmailStr | None = None
    address:        str | None = None
    blood_type:     PatientBloodType | None = None
    height_cm:      float | None = None
    weight_kg:      float | None = None
    blood_pressure: str | None = None
    photo_url:      str | None = None

    # -- name ----------------------------------------------------------------
    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("name must not be empty")
        return v

    # -- email ---------------------------------------------------------------
    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    # -- date_of_birth -------------------------------------------------------
    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: date) -> date:
        if v >= date.today():
            raise ValueError("date_of_birth must be a past date")
        return v

    # -- height_cm -----------------------------------------------------------
    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("height_cm must be greater than 0")
        return v

    # -- weight_kg -----------------------------------------------------------
    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("weight_kg must be greater than 0")
        return v

    # -- blood_pressure ------------------------------------------------------
    @field_validator("blood_pressure")
    @classmethod
    def validate_bp(cls, v: str | None) -> str | None:
        if v is not None and not _BP_RE.match(v):
            raise ValueError(
                "blood_pressure must be in systolic/diastolic format (e.g. 120/80)"
            )
        return v


# ---------------------------------------------------------------------------
# PatientUpdate  — every field is Optional; same validators apply when provided
# ---------------------------------------------------------------------------

class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:           Annotated[str, Field(min_length=1, max_length=255)] | None = None
    gender:         PatientGender | None = None
    date_of_birth:  date | None = None
    phone:          Annotated[str, Field(min_length=5, max_length=20)] | None = None
    email:          EmailStr | None = None
    address:        str | None = None
    blood_type:     PatientBloodType | None = None
    height_cm:      float | None = None
    weight_kg:      float | None = None
    blood_pressure: str | None = None
    photo_url:      str | None = None

    # -- name ----------------------------------------------------------------
    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    # -- email ---------------------------------------------------------------
    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    # -- date_of_birth -------------------------------------------------------
    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: date | None) -> date | None:
        if v is not None and v >= date.today():
            raise ValueError("date_of_birth must be a past date")
        return v

    # -- height_cm -----------------------------------------------------------
    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("height_cm must be greater than 0")
        return v

    # -- weight_kg -----------------------------------------------------------
    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("weight_kg must be greater than 0")
        return v

    # -- blood_pressure ------------------------------------------------------
    @field_validator("blood_pressure")
    @classmethod
    def validate_bp(cls, v: str | None) -> str | None:
        if v is not None and not _BP_RE.match(v):
            raise ValueError(
                "blood_pressure must be in systolic/diastolic format (e.g. 120/80)"
            )
        return v


# ---------------------------------------------------------------------------
# Response schemas (Part 2)
# Enums (PatientGender, PatientBloodType) reused from Part 1 — no re-definition.
# ---------------------------------------------------------------------------

def _calc_age(date_of_birth: date) -> int:
    """Shared age calculation used by PatientRead and PatientListItem."""
    today = date.today()
    age = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age


class PatientRead(BaseModel):
    """Full patient profile — returned by GET /patients/{id} and POST /patients."""

    model_config = ConfigDict(from_attributes=True)

    id:              uuid.UUID
    organization_id: uuid.UUID
    patient_code:    str
    name:            str
    gender:          PatientGender
    date_of_birth:   date
    phone:           str
    email:           str | None
    address:         str | None
    blood_type:      PatientBloodType | None
    height_cm:       float | None
    weight_kg:       float | None
    blood_pressure:  str | None
    photo_url:       str | None
    is_active:       bool
    created_at:      datetime
    updated_at:      datetime

    @computed_field
    @property
    def age(self) -> int:
        return _calc_age(self.date_of_birth)


class PatientListItem(BaseModel):
    """Lightweight patient row — returned inside PatientListResponse."""

    model_config = ConfigDict(from_attributes=True)

    id:            uuid.UUID
    patient_code:  str
    name:          str
    gender:        PatientGender
    phone:         str
    date_of_birth: date
    is_active:     bool
    created_at:    datetime

    @computed_field
    @property
    def age(self) -> int:
        return _calc_age(self.date_of_birth)


class PatientDemographicsResponse(BaseModel):
    """Aggregate demographics — returned by GET /patients/demographics."""

    model_config = ConfigDict(from_attributes=True)

    total_active:            int
    female_percentage:       float
    male_percentage:         float
    dominant_age_group:      str
    dominant_age_percentage: float


class PatientListResponse(BaseModel):
    """Paginated patient list — returned by GET /patients."""

    model_config = ConfigDict(from_attributes=True)

    patients: list[PatientListItem]
    total:    int
    page:     int
    limit:    int
