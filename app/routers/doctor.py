from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.doctor import (
    DoctorCreate,
    DoctorListItem,
    DoctorRead,
    DoctorStatus,
    DoctorStatsResponse,
    DoctorStatusUpdate,
    DoctorUpdate,
)
from app.services.doctor_service import (
    create_doctor,
    delete_doctor,
    get_doctor,
    get_doctor_stats,
    list_doctors,
    update_doctor,
    update_doctor_status,
)

router = APIRouter(prefix="/doctors", tags=["Doctors"])


class DoctorListResponse(BaseModel):
    doctors: list[DoctorListItem]
    total: int
    page: int
    limit: int


def _get_org_id(current_user: User) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.get("/stats", response_model=DoctorStatsResponse, status_code=status.HTTP_200_OK)
async def get_stats(
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> DoctorStatsResponse:
    org_id = _get_org_id(current_user)
    return await get_doctor_stats(db, org_id)


@router.get("", response_model=DoctorListResponse, status_code=status.HTTP_200_OK)
async def list_doctors_endpoint(
    search: str | None = None,
    specialization: str | None = None,
    status: DoctorStatus | None = None,
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> DoctorListResponse:
    org_id = _get_org_id(current_user)
    doctors, total = await list_doctors(db, org_id, search, specialization, status, page, limit)
    return DoctorListResponse(doctors=doctors, total=total, page=page, limit=limit)


@router.post("", response_model=DoctorRead, status_code=status.HTTP_201_CREATED)
async def create_doctor_endpoint(
    data: DoctorCreate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> DoctorRead:
    org_id = _get_org_id(current_user)
    return await create_doctor(db, org_id, data)


@router.get("/{doctor_id}", response_model=DoctorRead, status_code=status.HTTP_200_OK)
async def get_doctor_endpoint(
    doctor_id: UUID,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> DoctorRead:
    org_id = _get_org_id(current_user)
    return await get_doctor(db, doctor_id, org_id)


@router.put("/{doctor_id}", response_model=DoctorRead, status_code=status.HTTP_200_OK)
async def update_doctor_endpoint(
    doctor_id: UUID,
    data: DoctorUpdate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> DoctorRead:
    org_id = _get_org_id(current_user)
    return await update_doctor(db, doctor_id, org_id, data)


@router.patch("/{doctor_id}/status", response_model=DoctorRead, status_code=status.HTTP_200_OK)
async def update_doctor_status_endpoint(
    doctor_id: UUID,
    data: DoctorStatusUpdate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> DoctorRead:
    org_id = _get_org_id(current_user)
    return await update_doctor_status(db, doctor_id, org_id, data)


@router.delete("/{doctor_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def delete_doctor_endpoint(
    doctor_id: UUID,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = _get_org_id(current_user)
    await delete_doctor(db, doctor_id, org_id)
    return {"message": "Doctor deactivated successfully"}
