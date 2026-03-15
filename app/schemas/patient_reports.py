from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PatientReportBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                UUID
    report_type:       str
    file_name:         str
    file_size_kb:      int
    notes:             str | None
    created_at:        datetime
    doctor_name:       str | None
    organization_name: str | None
    file_url:          str | None  # signed URL, generated fresh on each request


class PatientReportsResponse(BaseModel):
    reports: list[PatientReportBrief]
    total:   int


class PatientUploadReportResponse(BaseModel):
    id:           UUID
    file_name:    str
    file_size_kb: int
    report_type:  str
    message:      str
