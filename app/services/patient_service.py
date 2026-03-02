from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import (
    PatientCreate,
    PatientUpdate,
    PatientDemographicsResponse,
    PatientGender,
)

_SORT_FIELDS: dict[str, object] = {
    "name":          Patient.name,
    "-name":         Patient.name,
    "date_of_birth": Patient.date_of_birth,
    "-date_of_birth":Patient.date_of_birth,
    "created_at":    Patient.created_at,
    "-created_at":   Patient.created_at,
}


async def _generate_patient_code(db: AsyncSession, org_id: UUID) -> str:
    """Return the next PID-NNNN code for the given organisation.

    Counts ALL patients (including soft-deleted) so codes are never reused
    after a soft delete.
    """
    result = await db.execute(
        select(func.count())
        .select_from(Patient)
        .where(Patient.organization_id == org_id)
    )
    count: int = result.scalar_one()
    next_number = count + 1
    return f"PID-{next_number:04d}"


async def create_patient(
    db: AsyncSession,
    org_id: UUID,
    data: PatientCreate,
) -> Patient:
    # -- duplicate phone guard (active patients only, scoped to org) --------
    duplicate = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.phone == data.phone,
            Patient.is_active == True,  # noqa: E712
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A patient with this phone number already exists",
        )

    patient_code = await _generate_patient_code(db, org_id)

    patient = Patient(
        organization_id=org_id,
        patient_code=patient_code,
        **data.model_dump(),
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


async def get_patient(
    db: AsyncSession,
    patient_id: UUID,
    org_id: UUID,
) -> Patient:
    result = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.id == patient_id,
            Patient.is_active == True,  # noqa: E712
        )
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )
    return patient


async def list_patients(
    db: AsyncSession,
    org_id: UUID,
    search: str | None,
    gender: PatientGender | None,
    date_from: date | None,
    date_to: date | None,
    sort: str | None,
    page: int,
    limit: int,
) -> tuple[list[Patient], int]:
    base_filters = [
        Patient.organization_id == org_id,
        Patient.is_active == True,  # noqa: E712
    ]

    if search:
        base_filters.append(Patient.name.ilike(f"%{search}%"))
    if gender is not None:
        base_filters.append(Patient.gender == gender.value)
    if date_from is not None:
        base_filters.append(Patient.date_of_birth >= date_from)
    if date_to is not None:
        base_filters.append(Patient.date_of_birth <= date_to)

    count_result = await db.execute(
        select(func.count()).select_from(Patient).where(*base_filters)
    )
    total: int = count_result.scalar_one()

    offset = (page - 1) * limit
    query = select(Patient).where(*base_filters).offset(offset).limit(limit)

    if sort and sort in _SORT_FIELDS:
        col = _SORT_FIELDS[sort]
        query = query.order_by(desc(col) if sort.startswith("-") else asc(col))
    else:
        query = query.order_by(asc(Patient.name))

    patients_result = await db.execute(query)
    patients = list(patients_result.scalars().all())

    return patients, total


async def update_patient(
    db: AsyncSession,
    patient_id: UUID,
    org_id: UUID,
    data: PatientUpdate,
) -> Patient:
    patient = await get_patient(db, patient_id, org_id)

    updates = data.model_dump(exclude_unset=True)

    if "phone" in updates and updates["phone"] != patient.phone:
        conflict = await db.execute(
            select(Patient).where(
                Patient.organization_id == org_id,
                Patient.phone == updates["phone"],
                Patient.is_active == True,  # noqa: E712
                Patient.id != patient_id,
            )
        )
        if conflict.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A patient with this phone number already exists",
            )

    for field, value in updates.items():
        setattr(patient, field, value)

    await db.commit()
    await db.refresh(patient)
    return patient


async def delete_patient(
    db: AsyncSession,
    patient_id: UUID,
    org_id: UUID,
) -> None:
    patient = await get_patient(db, patient_id, org_id)
    patient.is_active = False
    await db.commit()


async def get_patient_demographics(
    db: AsyncSession,
    org_id: UUID,
) -> PatientDemographicsResponse:
    base_filter = [Patient.organization_id == org_id, Patient.is_active == True]  # noqa: E712

    total_active = await db.scalar(select(func.count(Patient.id)).where(*base_filter)) or 0
    female_count = await db.scalar(
        select(func.count(Patient.id)).where(*base_filter, Patient.gender == PatientGender.female.value)
    ) or 0
    male_count = await db.scalar(
        select(func.count(Patient.id)).where(*base_filter, Patient.gender == PatientGender.male.value)
    ) or 0

    if total_active == 0:
        female_percentage = male_percentage = 0.0
    else:
        female_percentage = round(female_count / total_active * 100, 1)
        male_percentage = round(male_count / total_active * 100, 1)

    rows = await db.execute(select(Patient.date_of_birth).where(*base_filter))
    dobs = rows.scalars().all()

    buckets: dict[str, int] = {
        "0-17 years": 0,
        "18-24 years": 0,
        "25-40 years": 0,
        "41-60 years": 0,
        "60+ years": 0,
    }
    for dob in dobs:
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age <= 17:
            buckets["0-17 years"] += 1
        elif age <= 24:
            buckets["18-24 years"] += 1
        elif age <= 40:
            buckets["25-40 years"] += 1
        elif age <= 60:
            buckets["41-60 years"] += 1
        else:
            buckets["60+ years"] += 1

    if not dobs:
        dominant_age_group, dominant_age_percentage = "N/A", 0.0
    else:
        dominant_age_group = max(buckets, key=buckets.__getitem__)
        dominant_age_percentage = round(buckets[dominant_age_group] / total_active * 100, 1)

    return PatientDemographicsResponse(
        total_active=total_active,
        female_percentage=female_percentage,
        male_percentage=male_percentage,
        dominant_age_group=dominant_age_group,
        dominant_age_percentage=dominant_age_percentage,
    )
