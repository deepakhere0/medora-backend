import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.organization import HospitalRegistrationRequest, HospitalRegistrationResponse, OrganizationCreate


async def create_organization(
    db: AsyncSession, current_user: User | None, org_data: OrganizationCreate
) -> Organization:
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
        created_by=None,
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

    # Ensure user<->org link is intact (handles both new and legacy registrations)
    if organization.created_by is not None:
        result = await db.execute(
            select(User).where(User.id == organization.created_by)
        )
        user = result.scalar_one_or_none()
        if user is not None and user.organization_id != organization.id:
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


async def register_hospital(
    db: AsyncSession, data: HospitalRegistrationRequest
) -> HospitalRegistrationResponse:
    # 1. Check duplicate org name
    result = await db.execute(
        select(Organization).where(Organization.name == data.org_name)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this name already exists",
        )

    # 2. Check duplicate admin email
    result = await db.execute(
        select(User).where(User.email == data.admin_email)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # 3. Create Organization (is_approved=False by default)
    organization = Organization(
        name=data.org_name,
        city=data.org_city,
        state=data.org_state,
        address=data.org_address,
        phone=data.org_phone,
        email=data.org_email,
        is_approved=False,
        created_by=None,  # will be patched after user flush
    )
    db.add(organization)
    await db.flush()  # get org.id without committing

    # 4. Create admin User linked to the org
    user = User(
        email=data.admin_email,
        hashed_password=hash_password(data.admin_password),
        role=UserRole.org_admin,
        organization_id=organization.id,
        name=data.admin_name,
        phone=data.admin_phone,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # get user.id

    # 5. Back-link org → user
    organization.created_by = user.id

    # 6. Commit the entire transaction atomically
    await db.commit()
    await db.refresh(organization)
    await db.refresh(user)

    return HospitalRegistrationResponse(
        organization_id=organization.id,
        organization_name=organization.name,
        user_id=user.id,
        user_email=user.email,
        is_approved=organization.is_approved,
        message="Hospital registered successfully. Pending approval by Medora administration.",
    )
