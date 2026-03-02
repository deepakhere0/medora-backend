from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.patient import (
    PatientCreate,
    PatientUpdate,
    PatientRead,
    PatientListItem,
    PatientDemographicsResponse,
    PatientGender,
)
from app.services.patient_service import (
    create_patient,
    get_patient,
    list_patients,
    update_patient,
    delete_patient,
    get_patient_demographics,
)

router = APIRouter(prefix="/patients", tags=["Patients"])


class PatientListResponse(BaseModel):
    patients: list[PatientListItem]
    total:    int
    page:     int
    limit:    int


def _get_org_id(current_user: User) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.get(
    "/stats",
    response_model=PatientDemographicsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_stats(
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> PatientDemographicsResponse:
    org_id = _get_org_id(current_user)
    return await get_patient_demographics(db, org_id)


@router.get(
    "",
    response_model=PatientListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_patients_endpoint(
    search: str | None = None,
    gender: PatientGender | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str | None = None,
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> PatientListResponse:
    org_id = _get_org_id(current_user)
    patients, total = await list_patients(
        db, org_id, search, gender,
        date_from, date_to, sort, page, limit,
    )
    return PatientListResponse(
        patients=patients,
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{patient_id}",
    response_model=PatientRead,
    status_code=status.HTTP_200_OK,
)
async def get_patient_endpoint(
    patient_id: UUID,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> PatientRead:
    org_id = _get_org_id(current_user)
    return await get_patient(db, patient_id, org_id)


@router.post(
    "",
    response_model=PatientRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_endpoint(
    data: PatientCreate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> PatientRead:
    org_id = _get_org_id(current_user)
    return await create_patient(db, org_id, data)


@router.put(
    "/{patient_id}",
    response_model=PatientRead,
    status_code=status.HTTP_200_OK,
)
async def update_patient_endpoint(
    patient_id: UUID,
    data: PatientUpdate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> PatientRead:
    org_id = _get_org_id(current_user)
    return await update_patient(db, patient_id, org_id, data)


@router.delete(
    "/{patient_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def delete_patient_endpoint(
    patient_id: UUID,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = _get_org_id(current_user)
    await delete_patient(db, patient_id, org_id)
    return {"message": "Patient deactivated successfully"}
