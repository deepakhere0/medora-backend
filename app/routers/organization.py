import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.organization import OrganizationCreate, OrganizationResponse
from app.services.organization_service import (
    approve_organization,
    create_organization,
    get_pending_organizations,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_endpoint(
    org_data: OrganizationCreate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    return await create_organization(db, current_user, org_data)


@router.get("/pending", response_model=list[OrganizationResponse])
async def get_pending_organizations_endpoint(
    _: User = Depends(require_role(UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    return await get_pending_organizations(db)


@router.patch("/{org_id}/approve", response_model=OrganizationResponse)
async def approve_organization_endpoint(
    org_id: uuid.UUID,
    _: User = Depends(require_role(UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    return await approve_organization(db, org_id)
