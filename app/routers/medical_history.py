from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.medical_history import (
    MedicalHistoryCreate,
    MedicalHistoryListResponse,
    MedicalHistoryRead,
    MedicalHistoryUpdate,
)
from app.services.medical_history_service import (
    create_medical_history,
    delete_medical_history,
    get_patient_history,
    update_medical_history,
)


router = APIRouter(prefix="/medical-history", tags=["Medical History"])


def _get_org_id(current_user: User) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.post(
    "",
    response_model=MedicalHistoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_medical_history_endpoint(
    data: MedicalHistoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> MedicalHistoryRead:
    org_id = _get_org_id(current_user)
    return await create_medical_history(db, org_id, current_user.id, data)


@router.get(
    "/patient/{patient_id}",
    response_model=MedicalHistoryListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_patient_history_endpoint(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> MedicalHistoryListResponse:
    org_id = _get_org_id(current_user)
    return await get_patient_history(db, org_id, patient_id)


@router.patch(
    "/{history_id}",
    response_model=MedicalHistoryRead,
    status_code=status.HTTP_200_OK,
)
async def update_medical_history_endpoint(
    history_id: UUID,
    data: MedicalHistoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> MedicalHistoryRead:
    org_id = _get_org_id(current_user)
    return await update_medical_history(db, org_id, history_id, data)


@router.delete(
    "/{history_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def delete_medical_history_endpoint(
    history_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> dict:
    org_id = _get_org_id(current_user)
    await delete_medical_history(db, org_id, history_id)
    return {"message": "Medical history record deleted"}
