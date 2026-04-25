from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.patient_reports import (
    PatientReportDetailResponse,
    PatientReportUploadResponse,
    PatientReportsResponse,
    PatientUploadReportResponse,
)
from app.services.patient_report_service import (
    delete_patient_report,
    get_patient_report_by_id,
    get_patient_reports,
    upload_patient_report,
    upload_patient_report_enhanced,
)
from app.services.report_ai_service import run_ai_analysis_background
from app.services.report_upload_service import (
    VALID_UPLOAD_TYPES,
    delete_uploaded_file,
    get_public_url,
    upload_report_file,
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
    response_model=PatientReportUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_report(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    type: str = Form(...),
    doctor_name: str | None = Form(None),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
) -> PatientReportUploadResponse:
    if type not in VALID_UPLOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid type. Must be one of: {', '.join(sorted(VALID_UPLOAD_TYPES))}",
        )

    storage_path, public_url, file_type, file_size_bytes = await upload_report_file(
        file, current_patient.id
    )

    try:
        report = await upload_patient_report_enhanced(
            db,
            patient_id=current_patient.id,
            file_url=storage_path,
            public_url=public_url,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            title=title,
            upload_type=type,
            doctor_name=doctor_name,
            notes=notes,
        )
    except Exception:
        delete_uploaded_file(storage_path)
        raise

    is_image = file_type.startswith("image/")
    if is_image:
        background_tasks.add_task(
            run_ai_analysis_background, report.id, public_url, file_type
        )

    return PatientReportUploadResponse(
        id=report.id,
        title=report.title,
        upload_type=report.upload_type,
        doctor_name=report.doctor_name,
        file_url=public_url,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        ai_analysis_status=report.ai_analysis_status or "skipped",
        is_report_analysis=is_image,
        created_at=report.created_at,
    )


@router.get(
    "/{report_id}",
    response_model=PatientReportDetailResponse,
)
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
