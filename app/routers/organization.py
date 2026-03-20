import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationDetailResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organization_service import (
    approve_organization,
    create_organization,
    get_pending_organizations,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_endpoint(
    org_data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
):
    return await create_organization(db, None, org_data)


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


@router.get("/me", response_model=OrganizationDetailResponse)
async def get_my_organization(
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization linked to your account",
        )
    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


@router.put("/me", response_model=OrganizationDetailResponse)
async def update_my_organization(
    payload: OrganizationUpdate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization linked to your account",
        )
    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if payload.name is not None and payload.name != org.name:
        existing = await db.execute(
            select(Organization).where(Organization.name == payload.name)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An organization with this name already exists",
            )
        org.name = payload.name

    if payload.address is not None:
        org.address = payload.address
    if payload.city is not None:
        org.city = payload.city
    if payload.state is not None:
        org.state = payload.state
    if payload.phone is not None:
        org.phone = payload.phone
    if payload.email is not None:
        org.email = payload.email
    if payload.website is not None:
        org.website = payload.website

    await db.commit()
    await db.refresh(org)
    return org
