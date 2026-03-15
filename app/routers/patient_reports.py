from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.patient_reports import (
    PatientReportsResponse,
    PatientUploadReportResponse,
)
from app.services.patient_report_service import (
    delete_patient_report,
    get_patient_reports,
    upload_patient_report,
)


router = APIRouter(prefix="/patient/reports", tags=["Patient Reports"])


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


@router.post(
    "/upload",
    response_model=PatientUploadReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_report(
    file: UploadFile = File(...),
    report_type: str = Form(...),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
) -> PatientUploadReportResponse:
    report = await upload_patient_report(
        db,
        patient_id=current_patient.id,
        file=file,
        report_type=report_type,
        notes=notes,
    )
    return PatientUploadReportResponse(
        id=report.id,
        file_name=report.file_name,
        file_size_kb=report.file_size_kb,
        report_type=report.report_type,
        message="Report uploaded successfully",
    )


@router.delete("/{report_id}", status_code=status.HTTP_200_OK)
async def delete_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
) -> dict:
    await delete_patient_report(
        db,
        patient_id=current_patient.id,
        report_id=report_id,
    )
    return {"message": "Report deleted"}
