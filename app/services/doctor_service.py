from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor
from app.schemas.doctor import (
    DoctorCreate,
    DoctorStatus,
    DoctorStatusUpdate,
    DoctorStatsResponse,
    DoctorUpdate,
)


async def create_doctor(
    db: AsyncSession,
    org_id: UUID,
    data: DoctorCreate,
) -> Doctor:
    duplicate = await db.execute(
        select(Doctor).where(
            Doctor.organization_id == org_id,
            Doctor.license_number == data.license_number,
            Doctor.is_active == True,  # noqa: E712
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A doctor with this license number already exists in your organization",
        )

    doctor = Doctor(
        organization_id=org_id,
        **data.model_dump(),
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)
    return doctor


async def get_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    org_id: UUID,
) -> Doctor:
    result = await db.execute(
        select(Doctor).where(
            Doctor.organization_id == org_id,
            Doctor.id == doctor_id,
            Doctor.is_active == True,  # noqa: E712
        )
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )
    return doctor


async def list_doctors(
    db: AsyncSession,
    org_id: UUID,
    search: str | None,
    specialization: str | None,
    status: DoctorStatus | None,
    page: int,
    limit: int,
) -> tuple[list[Doctor], int]:
    base_filters = [
        Doctor.organization_id == org_id,
        Doctor.is_active == True,  # noqa: E712
    ]

    if search:
        base_filters.append(Doctor.name.ilike(f"%{search}%"))
    if specialization:
        base_filters.append(Doctor.specialization == specialization)
    if status:
        base_filters.append(Doctor.status == status.value)

    count_result = await db.execute(
        select(func.count()).select_from(Doctor).where(*base_filters)
    )
    total = count_result.scalar_one()

    offset = (page - 1) * limit
    doctors_result = await db.execute(
        select(Doctor).where(*base_filters).offset(offset).limit(limit)
    )
    doctors = list(doctors_result.scalars().all())

    return doctors, total


async def update_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    org_id: UUID,
    data: DoctorUpdate,
) -> Doctor:
    doctor = await get_doctor(db, doctor_id, org_id)

    updates = data.model_dump(exclude_unset=True)

    if "status" in updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the dedicated status endpoint to update doctor status",
        )

    if "license_number" in updates:
        duplicate = await db.execute(
            select(Doctor).where(
                Doctor.organization_id == org_id,
                Doctor.license_number == updates["license_number"],
                Doctor.is_active == True,  # noqa: E712
                Doctor.id != doctor_id,
            )
        )
        if duplicate.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A doctor with this license number already exists in your organization",
            )

    for field, value in updates.items():
        setattr(doctor, field, value)

    await db.commit()
    await db.refresh(doctor)
    return doctor


async def update_doctor_status(
    db: AsyncSession,
    doctor_id: UUID,
    org_id: UUID,
    data: DoctorStatusUpdate,
) -> Doctor:
    doctor = await get_doctor(db, doctor_id, org_id)
    doctor.status = data.status.value
    await db.commit()
    await db.refresh(doctor)
    return doctor


async def get_doctor_stats(
    db: AsyncSession,
    org_id: UUID,
) -> DoctorStatsResponse:
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    total_result = await db.execute(
        select(func.count()).select_from(Doctor).where(
            Doctor.organization_id == org_id,
            Doctor.is_active == True,  # noqa: E712
        )
    )
    on_duty_result = await db.execute(
        select(func.count()).select_from(Doctor).where(
            Doctor.organization_id == org_id,
            Doctor.status == DoctorStatus.on_duty.value,
        )
    )
    on_leave_result = await db.execute(
        select(func.count()).select_from(Doctor).where(
            Doctor.organization_id == org_id,
            Doctor.status == DoctorStatus.on_leave.value,
        )
    )
    new_this_week_result = await db.execute(
        select(func.count()).select_from(Doctor).where(
            Doctor.organization_id == org_id,
            Doctor.created_at >= seven_days_ago,
        )
    )

    return DoctorStatsResponse(
        total_doctors=total_result.scalar_one(),
        on_duty_count=on_duty_result.scalar_one(),
        on_leave_count=on_leave_result.scalar_one(),
        new_this_week=new_this_week_result.scalar_one(),
    )


async def delete_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    org_id: UUID,
) -> None:
    doctor = await get_doctor(db, doctor_id, org_id)
    doctor.is_active = False
    await db.commit()
