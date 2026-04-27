"""
Alias router: exposes patient report endpoints at /api/v1/reports
so mobile clients can use /api/v1/reports (GET list, GET /{id}).

The org-admin upload stays at POST /api/v1/reports/upload (different auth).
Patient upload stays at POST /api/v1/patient/reports/upload.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.patient_reports import PatientReportDetailResponse, PatientReportsResponse
from app.services.patient_report_service import get_patient_report_by_id, get_patient_reports
from app.services.report_upload_service import get_public_url

router = APIRouter(tags=["Patient Reports"])


@router.get("", response_model=PatientReportsResponse)
async def list_reports(
    report_type: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
) -> PatientReportsResponse:
    data = await get_patient_reports(
        db,
        patient_id=current_patient.id,
        report_type=report_type,
        search=search,
        skip=skip,
        limit=limit,
    )
    return PatientReportsResponse(**data)


@router.get("/{report_id}", response_model=PatientReportDetailResponse)
async def get_report_detail(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
) -> PatientReportDetailResponse:
    report = await get_patient_report_by_id(db, current_patient.id, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    file_url = get_public_url(report.file_url) if report.file_url else ""
    is_image = (report.file_type or "").startswith("image/")

    return PatientReportDetailResponse(
        id=report.id,
        title=report.title,
        upload_type=report.upload_type,
        doctor_name=report.doctor_name,
        file_url=file_url,
        file_type=report.file_type,
        file_size_bytes=report.file_size_bytes,
        ai_analysis=report.ai_analysis,
        ai_analysis_status=report.ai_analysis_status,
        is_report_analysis=is_image,
        notes=report.notes,
        report_type=report.report_type,
        created_at=report.created_at,
    )
