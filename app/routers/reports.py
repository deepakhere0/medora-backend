from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.report import (
    ReportCreate,
    ReportListResponse,
    ReportRead,
    ReportType,
)
from app.services.report_service import (
    delete_report,
    get_patient_reports,
    upload_report,
)


router = APIRouter(prefix="/reports", tags=["Reports"])


def _get_org_id(current_user: User) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.post(
    "/upload",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_report_endpoint(
    patient_id: UUID = Form(...),
    report_type: ReportType = Form(...),
    appointment_id: UUID | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> ReportRead:
    org_id = _get_org_id(current_user)
    data = ReportCreate(
        patient_id=patient_id,
        report_type=report_type,
        appointment_id=appointment_id,
        notes=notes,
    )
    return await upload_report(db, org_id, current_user.id, data, file)


@router.get(
    "/patient/{patient_id}",
    response_model=ReportListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_patient_reports_endpoint(
    patient_id: UUID,
    report_type: ReportType | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> ReportListResponse:
    org_id = _get_org_id(current_user)
    return await get_patient_reports(db, org_id, patient_id, report_type)


@router.delete(
    "/{report_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def delete_report_endpoint(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> dict:
    org_id = _get_org_id(current_user)
    await delete_report(db, org_id, report_id)
    return {"message": "Report deleted successfully"}
