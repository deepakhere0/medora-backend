import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportType(str, enum.Enum):
    prescription      = "prescription"
    lab_report        = "lab_report"
    xray              = "xray"
    discharge_summary = "discharge_summary"
    other             = "other"


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id:     UUID
    report_type:    ReportType
    appointment_id: UUID | None = None
    notes:          str | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:              UUID
    organization_id: UUID
    patient_id:      UUID
    appointment_id:  UUID | None
    uploaded_by:     UUID
    report_type:     ReportType
    file_name:       str
    file_size_kb:    int
    notes:           str | None
    is_active:       bool
    created_at:      datetime
    download_url:    str = ""


class ReportListResponse(BaseModel):
    reports: list[ReportRead]
    total:   int
