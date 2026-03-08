from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import delete_file, get_signed_url, upload_file
from app.models.appointment import Appointment, AppointmentStatus
from app.models.patient import Patient
from app.models.report import Report
from app.schemas.report import ReportCreate, ReportListResponse, ReportRead, ReportType


ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg":      "jpg",
    "image/png":       "png",
}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


async def upload_report(
    db: AsyncSession,
    org_id: UUID,
    uploaded_by: UUID,
    data: ReportCreate,
    file: UploadFile,
) -> ReportRead:
    # Validation 1 — Patient exists in this org
    patient_result = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.id == data.patient_id,
            Patient.is_active == True,
        )
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    # Validation 2 — Appointment (if provided)
    if data.appointment_id is not None:
        appt_result = await db.execute(
            select(Appointment).where(
                Appointment.organization_id == org_id,
                Appointment.id == data.appointment_id,
                Appointment.is_active == True,
            )
        )
        appointment = appt_result.scalar_one_or_none()
        if appointment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )
        if appointment.patient_id != data.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Appointment does not belong to this patient",
            )

    # Validation 3 — File type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File type not allowed. Use PDF, JPG, or PNG only",
        )

    # Validation 4 — File size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 20MB limit",
        )

    # Upload to Supabase Storage
    file_path = upload_file(
        file_bytes=file_bytes,
        file_name=file.filename,
        content_type=file.content_type,
        org_id=org_id,
        patient_id=data.patient_id,
    )

    # Calculate file size in KB
    file_size_kb = len(file_bytes) // 1024

    # Save to PostgreSQL
    report = Report(
        organization_id=org_id,
        patient_id=data.patient_id,
        appointment_id=data.appointment_id,
        uploaded_by=uploaded_by,
        report_type=data.report_type.value,
        file_url=file_path,
        file_name=file.filename,
        file_size_kb=file_size_kb,
        notes=data.notes,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Generate signed URL
    download_url = get_signed_url(report.file_url)

    # Build and return ReportRead
    result = ReportRead.model_validate(report)
    result.download_url = download_url
    return result


async def get_patient_reports(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
    report_type: ReportType | None = None,
) -> ReportListResponse:
    # Validate patient exists in this org
    patient_result = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.id == patient_id,
            Patient.is_active == True,
        )
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    # Build query
    filters = [
        Report.organization_id == org_id,
        Report.patient_id == patient_id,
        Report.is_active == True,
    ]
    if report_type is not None:
        filters.append(Report.report_type == report_type.value)

    reports_result = await db.execute(
        select(Report).where(*filters).order_by(Report.created_at.desc())
    )
    reports = reports_result.scalars().all()

    # Generate signed URLs and build response
    report_reads: list[ReportRead] = []
    for report in reports:
        download_url = get_signed_url(report.file_url)
        result = ReportRead.model_validate(report)
        result.download_url = download_url
        report_reads.append(result)

    return ReportListResponse(
        reports=report_reads,
        total=len(report_reads),
    )


async def delete_report(
    db: AsyncSession,
    org_id: UUID,
    report_id: UUID,
) -> None:
    # Fetch report
    report_result = await db.execute(
        select(Report).where(
            Report.organization_id == org_id,
            Report.id == report_id,
            Report.is_active == True,
        )
    )
    report = report_result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    # Delete from Supabase Storage
    delete_file(report.file_url)

    # Soft delete in PostgreSQL
    report.is_active = False
    await db.commit()
