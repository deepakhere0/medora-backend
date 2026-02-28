import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.organization import OrganizationCreate


async def create_organization(
    db: AsyncSession, current_user: User, org_data: OrganizationCreate
) -> Organization:
    if current_user.role != UserRole.org_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only org_admin users can create an organization",
        )

    result = await db.execute(
        select(Organization).where(Organization.created_by == current_user.id)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already created an organization",
        )

    result = await db.execute(
        select(Organization).where(Organization.name == org_data.name)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization name already exists",
        )

    organization = Organization(
        name=org_data.name,
        city=org_data.city,
        state=org_data.state,
        created_by=current_user.id,
    )
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return organization


async def get_organization(db: AsyncSession, organization_id: uuid.UUID) -> Organization | None:
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    return result.scalar_one_or_none()


async def approve_organization(
    db: AsyncSession, org_id: uuid.UUID
) -> Organization:
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    organization = result.scalar_one_or_none()

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if organization.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is already approved",
        )

    organization.is_approved = True

    result = await db.execute(
        select(User).where(User.id == organization.created_by)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization creator user not found",
        )

    user.organization_id = organization.id

    await db.commit()
    await db.refresh(organization)
    return organization


async def get_pending_organizations(db: AsyncSession) -> list[Organization]:
    result = await db.execute(
        select(Organization).where(Organization.is_approved == False)  # noqa: E712
    )
    return list(result.scalars().all())


async def get_all_organizations(db: AsyncSession) -> list[Organization]:
    result = await db.execute(select(Organization))
    return list(result.scalars().all())
