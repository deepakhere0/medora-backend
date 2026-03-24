from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminOrgBrief,
    AdminOrgsResponse,
    AdminStatsResponse,
    AdminUserBrief,
    AdminUsersResponse,
)


async def get_all_users(
    db: AsyncSession,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> AdminUsersResponse:
    base_stmt = (
        select(User, Organization.name.label("org_name"))
        .outerjoin(Organization, User.organization_id == Organization.id)
    )

    if role is not None:
        base_stmt = base_stmt.where(User.role == role)
    if is_active is not None:
        base_stmt = base_stmt.where(User.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        base_stmt = base_stmt.where(
            or_(User.email.ilike(pattern), User.name.ilike(pattern))
        )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    rows = (
        await db.execute(
            base_stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        )
    ).all()

    users = [
        AdminUserBrief(
            id=row.User.id,
            email=row.User.email,
            name=row.User.name,
            phone=row.User.phone,
            role=row.User.role,
            is_active=row.User.is_active,
            organization_id=row.User.organization_id,
            organization_name=row.org_name,
            created_at=row.User.created_at,
        )
        for row in rows
    ]

    return AdminUsersResponse(users=users, total=total)


async def toggle_user_active(
    db: AsyncSession,
    user_id: UUID,
    is_active: bool,
    current_user_id: UUID,
) -> AdminUserBrief:
    if user_id == current_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own active status",
        )

    result = await db.execute(
        select(User, Organization.name.label("org_name"))
        .outerjoin(Organization, User.organization_id == Organization.id)
        .where(User.id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.execute(update(User).where(User.id == user_id).values(is_active=is_active))
    await db.commit()

    return AdminUserBrief(
        id=row.User.id,
        email=row.User.email,
        name=row.User.name,
        phone=row.User.phone,
        role=row.User.role,
        is_active=is_active,
        organization_id=row.User.organization_id,
        organization_name=row.org_name,
        created_at=row.User.created_at,
    )


async def update_user_role(
    db: AsyncSession,
    user_id: UUID,
    new_role: str,
) -> AdminUserBrief:
    valid_roles = {r.value for r in UserRole}
    if new_role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}",
        )

    result = await db.execute(
        select(User, Organization.name.label("org_name"))
        .outerjoin(Organization, User.organization_id == Organization.id)
        .where(User.id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.execute(update(User).where(User.id == user_id).values(role=new_role))
    await db.commit()

    return AdminUserBrief(
        id=row.User.id,
        email=row.User.email,
        name=row.User.name,
        phone=row.User.phone,
        role=new_role,
        is_active=row.User.is_active,
        organization_id=row.User.organization_id,
        organization_name=row.org_name,
        created_at=row.User.created_at,
    )


async def get_admin_stats(db: AsyncSession) -> AdminStatsResponse:
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_organizations = (await db.execute(select(func.count(Organization.id)))).scalar_one()
    total_patients = (await db.execute(select(func.count(Patient.id)))).scalar_one()
    total_doctors = (
        await db.execute(select(func.count(Doctor.id)).where(Doctor.is_active == True))
    ).scalar_one()
    total_appointments = (await db.execute(select(func.count(Appointment.id)))).scalar_one()
    pending_approvals = (
        await db.execute(
            select(func.count(Organization.id)).where(Organization.is_approved == False)
        )
    ).scalar_one()

    return AdminStatsResponse(
        total_users=total_users,
        total_organizations=total_organizations,
        total_patients=total_patients,
        total_doctors=total_doctors,
        total_appointments=total_appointments,
        pending_approvals=pending_approvals,
    )


async def get_all_organizations(db: AsyncSession) -> AdminOrgsResponse:
    # Subqueries for doctor and patient counts per org
    doctor_counts = (
        select(Doctor.organization_id, func.count(Doctor.id).label("cnt"))
        .where(Doctor.is_active == True)
        .group_by(Doctor.organization_id)
        .subquery()
    )
    patient_counts = (
        select(Patient.organization_id, func.count(Patient.id).label("cnt"))
        .group_by(Patient.organization_id)
        .subquery()
    )
    # Join org with its creator user (for admin email) and count subqueries
    admin_user = User.__table__.alias("admin_user")
    stmt = (
        select(
            Organization,
            admin_user.c.email.label("admin_email"),
            func.coalesce(doctor_counts.c.cnt, 0).label("doctor_count"),
            func.coalesce(patient_counts.c.cnt, 0).label("patient_count"),
        )
        .outerjoin(admin_user, Organization.created_by == admin_user.c.id)
        .outerjoin(doctor_counts, Organization.id == doctor_counts.c.organization_id)
        .outerjoin(patient_counts, Organization.id == patient_counts.c.organization_id)
        .order_by(Organization.created_at.desc())
    )

    rows = (await db.execute(stmt)).all()
    total = len(rows)

    orgs = [
        AdminOrgBrief(
            id=row.Organization.id,
            name=row.Organization.name,
            city=row.Organization.city,
            state=row.Organization.state,
            is_approved=row.Organization.is_approved,
            admin_email=row.admin_email,
            doctor_count=row.doctor_count,
            patient_count=row.patient_count,
            created_at=row.Organization.created_at,
        )
        for row in rows
    ]

    return AdminOrgsResponse(organizations=orgs, total=total)
