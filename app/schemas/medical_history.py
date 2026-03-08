from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MedicalHistoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id:     UUID
    appointment_id: UUID | None = None
    event_date:     date
    event_name:     str = Field(..., min_length=2, max_length=255)
    description:    str = Field(..., min_length=5)

    @field_validator("event_date")
    @classmethod
    def event_date_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Event date cannot be in the future")
        return v


class MedicalHistoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_date:  date | None = None
    event_name:  str | None = Field(None, min_length=2, max_length=255)
    description: str | None = Field(None, min_length=5)

    @field_validator("event_date")
    @classmethod
    def event_date_not_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("Event date cannot be in the future")
        return v


class MedicalHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:              UUID
    organization_id: UUID
    patient_id:      UUID
    appointment_id:  UUID | None
    recorded_by:     UUID
    event_date:      date
    event_name:      str
    description:     str
    is_active:       bool
    created_at:      datetime


class MedicalHistoryListResponse(BaseModel):
    histories: list[MedicalHistoryRead]
    total:     int
