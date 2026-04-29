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
    # Patient self-upload fields (None for legacy org-admin uploads)
    title:             str | None = None
    upload_type:       str | None = None
    file_type:         str | None = None
    ai_analysis_status: str | None = None
    is_report_analysis: bool = False


class PatientReportsResponse(BaseModel):
    reports: list[PatientReportBrief]
    total:   int


class PatientUploadReportResponse(BaseModel):
    id:           UUID
    file_name:    str
    file_size_kb: int
    report_type:  str
    message:      str


# ---------------------------------------------------------------------------
# Enhanced patient self-upload responses (with AI analysis)
# ---------------------------------------------------------------------------

class PatientReportUploadResponse(BaseModel):
    id:                 UUID
    title:              str | None
    upload_type:        str | None
    doctor_name:        str | None
    file_url:           str           # public URL
    file_type:          str
    file_size_bytes:    int
    ai_analysis_status: str
    is_report_analysis: bool
    created_at:         datetime


class PatientReportDetailResponse(BaseModel):
    id:                 UUID
    title:              str | None
    upload_type:        str | None
    doctor_name:        str | None
    file_url:           str           # public URL
    file_type:          str | None
    file_size_bytes:    int | None
    ai_analysis:        str | None
    ai_analysis_status: str | None
    is_report_analysis: bool
    notes:              str | None
    report_type:        str | None
    created_at:         datetime
    # OCR pipeline fields (populated asynchronously after upload)
    extracted_text:     str | None = None   # raw Vision API output
    clean_text:         str | None = None   # normalised OCR text
