from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminDoctorBrief,
    AdminDoctorDetail,
    AdminDoctorsResponse,
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
            address=row.Organization.address,
            pincode=row.Organization.pincode,
            phone=row.Organization.phone,
            is_approved=row.Organization.is_approved,
            admin_email=row.admin_email,
            doctor_count=row.doctor_count,
            patient_count=row.patient_count,
            registration_number=row.Organization.registration_number,
            registration_certificate_url=row.Organization.registration_certificate_url,
            created_at=row.Organization.created_at,
        )
        for row in rows
    ]

    return AdminOrgsResponse(organizations=orgs, total=total)


# ---------------------------------------------------------------------------
# Doctor verification management
# ---------------------------------------------------------------------------

def _doctor_verification_status(doctor: Doctor, user_is_active: bool) -> str:
    """Derive a human-readable verification status from DB fields."""
    if doctor.is_verified and user_is_active:
        return "verified"
    if doctor.is_verified and not user_is_active:
        return "suspended"
    if not doctor.is_verified and doctor.rejection_reason is not None:
        return "rejected"
    return "pending"


async def get_all_doctors_admin(
    db: AsyncSession,
    verification_status: str = "all",
    page: int = 1,
    per_page: int = 20,
) -> AdminDoctorsResponse:
    """List doctors with optional filter by verification status."""
    stmt = (
        select(Doctor, User.is_active.label("user_is_active"))
        .outerjoin(User, Doctor.user_id == User.id)
        .where(Doctor.self_registered == True)  # noqa: E712
    )

    if verification_status == "pending":
        stmt = stmt.where(
            Doctor.is_verified == False,  # noqa: E712
            Doctor.rejection_reason == None,  # noqa: E711
            User.is_active == False,  # noqa: E712
        )
    elif verification_status == "verified":
        stmt = stmt.where(
            Doctor.is_verified == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    elif verification_status == "rejected":
        stmt = stmt.where(
            Doctor.is_verified == False,  # noqa: E712
            Doctor.rejection_reason != None,  # noqa: E711
        )
    elif verification_status == "suspended":
        stmt = stmt.where(
            Doctor.is_verified == True,  # noqa: E712
            User.is_active == False,  # noqa: E712
        )
    # "all" — no additional filter

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()
    total_pages = max(1, -(-total // per_page))  # ceiling division

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            stmt.order_by(Doctor.created_at.desc()).offset(offset).limit(per_page)
        )
    ).all()

    doctors = [
        AdminDoctorBrief(
            id=row.Doctor.id,
            name=row.Doctor.name,
            email=row.Doctor.email,
            phone=row.Doctor.phone,
            specialty=row.Doctor.specialty,
            nmc_registration_number=row.Doctor.nmc_registration_number,
            is_verified=row.Doctor.is_verified,
            is_active=bool(row.user_is_active),
            rejection_reason=row.Doctor.rejection_reason,
            city=row.Doctor.city,
            state=row.Doctor.state,
            profile_photo_url=row.Doctor.profile_photo_url,
            registration_certificate_url=row.Doctor.registration_certificate_url,
            created_at=row.Doctor.created_at,
            verification_status=_doctor_verification_status(
                row.Doctor, bool(row.user_is_active)
            ),
        )
        for row in rows
    ]

    return AdminDoctorsResponse(
        doctors=doctors,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


async def get_doctor_detail_admin(db: AsyncSession, doctor_id: UUID) -> AdminDoctorDetail:
    """Full doctor record for the admin detail view."""
    result = await db.execute(
        select(Doctor, User.is_active.label("user_is_active"))
        .outerjoin(User, Doctor.user_id == User.id)
        .where(Doctor.id == doctor_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    doc = row.Doctor
    user_is_active = bool(row.user_is_active)

    return AdminDoctorDetail(
        id=doc.id,
        name=doc.name,
        email=doc.email,
        phone=doc.phone,
        specialty=doc.specialty,
        specialization=doc.specialization,
        degree=doc.degree,
        nmc_registration_number=doc.nmc_registration_number,
        is_verified=doc.is_verified,
        is_active=user_is_active,
        rejection_reason=doc.rejection_reason,
        verification_status=_doctor_verification_status(doc, user_is_active),
        city=doc.city,
        state=doc.state,
        address=doc.address,
        pincode=doc.pincode,
        latitude=doc.latitude,
        longitude=doc.longitude,
        profile_photo_url=doc.profile_photo_url,
        registration_certificate_url=doc.registration_certificate_url,
        consultation_fee=doc.consultation_fee,
        online_consultation_fee=doc.online_consultation_fee,
        is_available_online=doc.is_available_online,
        experience_years=doc.experience_years,
        about_text=doc.about_text,
        languages_spoken=doc.languages_spoken,
        average_rating=doc.average_rating,
        total_reviews=doc.total_reviews,
        is_independent=doc.is_independent,
        self_registered=doc.self_registered,
        user_id=doc.user_id,
        organization_id=doc.organization_id,
        created_at=doc.created_at,
    )


async def verify_doctor(db: AsyncSession, doctor_id: UUID) -> AdminDoctorDetail:
    """Approve a doctor: set is_verified=True, activate user account."""
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    # Clear rejection_reason in case this is a re-verification after rejection
    await db.execute(
        update(Doctor)
        .where(Doctor.id == doctor_id)
        .values(is_verified=True, rejection_reason=None)
    )
    if doctor.user_id is not None:
        await db.execute(
            update(User).where(User.id == doctor.user_id).values(is_active=True)
        )
    await db.commit()

    return await get_doctor_detail_admin(db, doctor_id)


async def reject_doctor(
    db: AsyncSession, doctor_id: UUID, reason: str | None
) -> AdminDoctorDetail:
    """Reject a doctor registration: set is_verified=False, keep user inactive, store reason."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    await db.execute(
        update(Doctor)
        .where(Doctor.id == doctor_id)
        .values(is_verified=False, rejection_reason=reason or "Rejected by administrator")
    )
    if doctor.user_id is not None:
        await db.execute(
            update(User).where(User.id == doctor.user_id).values(is_active=False)
        )
    await db.commit()

    return await get_doctor_detail_admin(db, doctor_id)


async def suspend_doctor(db: AsyncSession, doctor_id: UUID) -> AdminDoctorDetail:
    """Suspend a verified doctor: keep is_verified=True but deactivate user account."""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    if doctor.user_id is not None:
        await db.execute(
            update(User).where(User.id == doctor.user_id).values(is_active=False)
        )
    await db.commit()

    return await get_doctor_detail_admin(db, doctor_id)


async def delete_doctor_cascade(db: AsyncSession, doctor_id: UUID) -> None:
    """Hard delete a doctor and all associated records, including the linked user account."""
    result = await db.execute(
        select(Doctor.user_id).where(Doctor.id == doctor_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    user_id = row.user_id
    doc_id_str = str(doctor_id)

    # Cascade order: child tables first, then doctor, then user
    await db.execute(
        text("DELETE FROM reviews WHERE doctor_id = :doctor_id"),
        {"doctor_id": doc_id_str},
    )
    await db.execute(
        text("DELETE FROM online_consultations WHERE doctor_id = :doctor_id"),
        {"doctor_id": doc_id_str},
    )
    await db.execute(
        text("DELETE FROM doctor_schedules WHERE doctor_id = :doctor_id"),
        {"doctor_id": doc_id_str},
    )
    await db.execute(
        text("DELETE FROM appointments WHERE doctor_id = :doctor_id"),
        {"doctor_id": doc_id_str},
    )
    await db.execute(
        text("DELETE FROM doctors WHERE id = :doctor_id"),
        {"doctor_id": doc_id_str},
    )
    if user_id is not None:
        await db.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": str(user_id)},
        )
    await db.commit()
