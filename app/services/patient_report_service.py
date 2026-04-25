from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.storage import delete_file, get_signed_url, upload_file
from app.models.appointment import Appointment
from app.models.patient_organization import PatientOrganization
from app.models.report import Report


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

_VALID_REPORT_TYPES = {"prescription", "lab_report", "xray", "discharge_summary", "other"}


async def get_patient_reports(
    db: AsyncSession,
    patient_id: UUID,
    report_type: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> dict:
    filters = [
        Report.patient_id == patient_id,
        Report.is_active == True,
    ]
    if report_type:
        filters.append(Report.report_type == report_type)
    if search:
        filters.append(Report.file_name.ilike(f"%{search}%"))

    # Total count
    count_result = await db.execute(
        select(func.count(Report.id)).where(*filters)
    )
    total = count_result.scalar_one()

    # Paginated data with eager-loaded relationships
    result = await db.execute(
        select(Report)
        .where(*filters)
        .options(
            selectinload(Report.organization),
            selectinload(Report.appointment).selectinload(Appointment.doctor),
        )
        .order_by(Report.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    reports = result.scalars().all()

    report_list = []
    for report in reports:
        # Generate a fresh signed URL; fail gracefully if storage is unreachable
        file_url: str | None = None
        try:
            file_url = get_signed_url(report.file_url)
        except HTTPException:
            pass

        doctor_name: str | None = None
        if report.appointment and report.appointment.doctor:
            doctor_name = report.appointment.doctor.name

        organization_name: str | None = None
        if report.organization:
            organization_name = report.organization.name

        report_list.append({
            "id":                report.id,
            "report_type":       report.report_type,
            "file_name":         report.file_name,
            "file_size_kb":      report.file_size_kb,
            "notes":             report.notes,
            "created_at":        report.created_at,
            "doctor_name":       doctor_name,
            "organization_name": organization_name,
            "file_url":          file_url,
        })

    return {"reports": report_list, "total": total}


async def upload_patient_report(
    db: AsyncSession,
    patient_id: UUID,
    file: UploadFile,
    report_type: str,
    notes: str | None,
) -> Report:
    # Validate report_type
    if report_type not in _VALID_REPORT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid report type. Must be one of: {', '.join(sorted(_VALID_REPORT_TYPES))}",
        )

    # Validate file type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File type not allowed. Use PDF, DOCX, JPG, or PNG only",
        )

    # Read and validate file size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10 MB limit",
        )

    # Determine organization_id: use first active linked org, or None
    org_result = await db.execute(
        select(PatientOrganization)
        .where(
            PatientOrganization.patient_id == patient_id,
            PatientOrganization.is_active == True,
        )
        .limit(1)
    )
    po = org_result.scalar_one_or_none()
    org_id: UUID | None = po.organization_id if po else None

    # Upload to Supabase Storage.
    # For unlinked patients, use patient_id as the org folder so the path remains
    # unique and scoped: {patient_id}/{patient_id}/{timestamp}_{filename}
    upload_org_id = org_id if org_id is not None else patient_id
    file_path = upload_file(
        file_bytes=file_bytes,
        file_name=file.filename or "upload",
        content_type=file.content_type,
        org_id=upload_org_id,
        patient_id=patient_id,
    )

    file_size_kb = max(1, len(file_bytes) // 1024)

    report = Report(
        organization_id=org_id,          # None for unlinked self-uploads
        patient_id=patient_id,
        appointment_id=None,
        uploaded_by=None,                # None marks this as a patient self-upload
        report_type=report_type,
        file_url=file_path,
        file_name=file.filename or "upload",
        file_size_kb=file_size_kb,
        notes=notes,
        is_active=True,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return report


async def upload_patient_report_enhanced(
    db: AsyncSession,
    patient_id: UUID,
    file_url: str,
    public_url: str,
    file_type: str,
    file_size_bytes: int,
    title: str | None,
    upload_type: str | None,
    doctor_name: str | None,
    notes: str | None,
) -> Report:
    """
    Insert a Report row for a patient self-upload after the file is already in Supabase.
    Raises on DB failure — caller is responsible for deleting the uploaded file on error.
    """
    report = Report(
        organization_id=None,
        patient_id=patient_id,
        appointment_id=None,
        uploaded_by=None,
        report_type="other",          # legacy required column; upload_type carries the real value
        file_url=file_url,            # storage path
        file_name=f"{upload_type or 'report'}.{file_type.split('/')[-1]}",
        file_size_kb=max(1, file_size_bytes // 1024),
        notes=notes,
        is_active=True,
        title=title,
        upload_type=upload_type,
        doctor_name=doctor_name,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        ai_analysis=None,
        ai_analysis_status="pending" if file_type.startswith("image/") else "skipped",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def get_patient_report_by_id(
    db: AsyncSession,
    patient_id: UUID,
    report_id: UUID,
) -> Report | None:
    """Fetch a single report owned by this patient, or None if not found / not owned."""
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.patient_id == patient_id,
            Report.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def delete_patient_report(
    db: AsyncSession,
    patient_id: UUID,
    report_id: UUID,
) -> None:
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.patient_id == patient_id,
            Report.is_active == True,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    # Patients may only delete reports they uploaded themselves
    if report.uploaded_by is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reports uploaded by hospital staff cannot be deleted by patients",
        )

    # Remove from Supabase Storage; continue with soft-delete even if storage fails
    try:
        delete_file(report.file_url)
    except HTTPException:
        pass

    report.is_active = False
    await db.commit()
