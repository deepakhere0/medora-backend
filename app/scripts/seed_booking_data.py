"""
Seed script for MEDORA booking flow test data.

Run with:
    python -m app.scripts.seed_booking_data

Idempotent: skips any organization that already exists by name.
"""

import asyncio
import random
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Register all models so SQLAlchemy's mapper is fully populated
import app.models  # noqa: F401

from app.db.session import AsyncSessionLocal
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.organization import Organization


# ---------------------------------------------------------------------------
# Seed definitions
# ---------------------------------------------------------------------------

ORGS = [
    {
        "name": "Shree Ganesh Hospital",
        "state": "Maharashtra",
        "city": "Pune",
        "address": "45 Karve Road, Deccan Gymkhana, Pune 411004",
    },
    {
        "name": "City Care Multispecialty Hospital",
        "state": "Maharashtra",
        "city": "Pune",
        "address": "12 MG Road, Camp Area, Pune 411001",
    },
    {
        "name": "Aarogya Health Center",
        "state": "Maharashtra",
        "city": "Nagpur",
        "address": "78 Dharampeth, Nagpur 440010",
    },
    {
        "name": "Rajiv Gandhi Medical Institute",
        "state": "Rajasthan",
        "city": "Jaipur",
        "address": "23 Tonk Road, Jaipur 302015",
    },
    {
        "name": "Sanjivani Hospital",
        "state": "Rajasthan",
        "city": "Jaipur",
        "address": "56 MI Road, Jaipur 302001",
    },
    {
        "name": "Life Line Hospital",
        "state": "Gujarat",
        "city": "Surat",
        "address": "89 Ring Road, Surat 395002",
    },
]

# Each entry: (full_name, specialization, experience_years, gender, org_name, saturday_schedule)
# saturday_schedule=True → also gets a Saturday morning block
DOCTORS = [
    # Shree Ganesh Hospital (Pune)
    ("Dr. Anil Deshmukh",    "Cardiology",         15, "male",   "Shree Ganesh Hospital",             True),
    ("Dr. Priya Kulkarni",   "Pediatrics",         10, "female", "Shree Ganesh Hospital",             False),
    ("Dr. Rajesh Patil",     "Orthopedic Surgery", 12, "male",   "Shree Ganesh Hospital",             False),
    ("Dr. Sneha Joshi",      "Dermatology",         8, "female", "Shree Ganesh Hospital",             False),
    # City Care Multispecialty Hospital (Pune)
    ("Dr. Vikram Mehta",     "Neurology",          20, "male",   "City Care Multispecialty Hospital", True),
    ("Dr. Anjali Shah",      "Gynecology",         14, "female", "City Care Multispecialty Hospital", False),
    # Aarogya Health Center (Nagpur)
    ("Dr. Suresh Iyer",      "General Medicine",   18, "male",   "Aarogya Health Center",             False),
    ("Dr. Meena Reddy",      "ENT",                11, "female", "Aarogya Health Center",             False),
    # Rajiv Gandhi Medical Institute (Jaipur)
    ("Dr. Amit Sharma",      "Cardiology",         16, "male",   "Rajiv Gandhi Medical Institute",    True),
    ("Dr. Kavita Gupta",     "Pediatrics",          9, "female", "Rajiv Gandhi Medical Institute",    False),
    ("Dr. Ravi Agarwal",     "Orthopedic Surgery", 13, "male",   "Rajiv Gandhi Medical Institute",    False),
    # Sanjivani Hospital (Jaipur)
    ("Dr. Neha Verma",       "Dermatology",         7, "female", "Sanjivani Hospital",                False),
    # Life Line Hospital (Surat)
    ("Dr. Manoj Patel",      "General Medicine",   22, "male",   "Life Line Hospital",                True),
    ("Dr. Divya Nair",       "Gynecology",         10, "female", "Life Line Hospital",                False),
]


def _random_license() -> str:
    return f"MCI-{random.randint(100000, 999999)}"


def _random_phone() -> str:
    prefix = random.choice(["9", "8"])
    rest = "".join([str(random.randint(0, 9)) for _ in range(9)])
    return prefix + rest


def _doctor_email(full_name: str, org_name: str) -> str:
    # "Dr. Anil Deshmukh" → "anil.deshmukh"
    parts = full_name.replace("Dr. ", "").lower().split()
    local = ".".join(parts)
    domain = org_name.lower().replace(" ", "").replace(".", "") + ".com"
    return f"{local}@{domain}"


# ---------------------------------------------------------------------------
# Core seed logic
# ---------------------------------------------------------------------------

async def seed(db: AsyncSession) -> None:
    orgs_created = 0
    doctors_created = 0
    schedules_created = 0

    # --- Organizations ---
    org_map: dict[str, Organization] = {}

    for org_data in ORGS:
        result = await db.execute(
            select(Organization).where(Organization.name == org_data["name"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  [skip] Org already exists: {org_data['name']}")
            org_map[org_data["name"]] = existing
        else:
            org = Organization(
                name=org_data["name"],
                state=org_data["state"],
                city=org_data["city"],
                address=org_data["address"],
                is_approved=True,
            )
            db.add(org)
            await db.flush()  # populate org.id before referencing it
            org_map[org_data["name"]] = org
            orgs_created += 1
            print(f"  [+] Created org: {org.name}  ({org.city}, {org.state})")

    # --- Doctors ---
    doctor_map: dict[str, Doctor] = {}  # full_name → Doctor

    for (full_name, specialization, exp_years, gender, org_name, saturday) in DOCTORS:
        org = org_map[org_name]

        # Check by name + org to avoid duplicates
        result = await db.execute(
            select(Doctor)
            .where(Doctor.organization_id == org.id)
            .where(Doctor.name == full_name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  [skip] Doctor already exists: {full_name}")
            doctor_map[full_name] = existing
        else:
            doctor = Doctor(
                organization_id=org.id,
                name=full_name,
                specialization=specialization,
                experience_years=exp_years,
                gender=gender,
                license_number=_random_license(),
                license_expiry=date(2027, 12, 31),
                employment_type="full_time",
                status="active",
                is_active=True,
                email=_doctor_email(full_name, org_name),
                phone=_random_phone(),
            )
            db.add(doctor)
            await db.flush()
            doctor_map[full_name] = doctor
            doctors_created += 1
            print(f"  [+] Created doctor: {full_name}  ({specialization}, {org_name})")

    # --- Doctor Schedules ---
    for (full_name, _spec, _exp, _gender, _org, saturday) in DOCTORS:
        doctor = doctor_map[full_name]

        # Monday–Friday (0–4)
        for dow in range(5):
            result = await db.execute(
                select(DoctorSchedule)
                .where(DoctorSchedule.doctor_id == doctor.id)
                .where(DoctorSchedule.day_of_week == dow)
            )
            if result.scalar_one_or_none():
                continue  # already seeded

            schedule = DoctorSchedule(
                doctor_id=doctor.id,
                organization_id=doctor.organization_id,
                day_of_week=dow,
                start_time=time(9, 0),
                end_time=time(17, 0),
                slot_duration_minutes=30,
                break_start=time(13, 0),
                break_end=time(14, 0),
                is_active=True,
            )
            db.add(schedule)
            schedules_created += 1

        # Saturday morning (optional)
        if saturday:
            result = await db.execute(
                select(DoctorSchedule)
                .where(DoctorSchedule.doctor_id == doctor.id)
                .where(DoctorSchedule.day_of_week == 5)
            )
            if not result.scalar_one_or_none():
                schedule = DoctorSchedule(
                    doctor_id=doctor.id,
                    organization_id=doctor.organization_id,
                    day_of_week=5,
                    start_time=time(9, 0),
                    end_time=time(13, 0),
                    slot_duration_minutes=30,
                    break_start=None,
                    break_end=None,
                    is_active=True,
                )
                db.add(schedule)
                schedules_created += 1

        if schedules_created > 0:
            print(f"  [+] Schedules created for: {full_name}")

    await db.commit()

    print()
    print("=" * 50)
    print(f"  Seed complete.")
    print(f"  Orgs created    : {orgs_created}")
    print(f"  Doctors created : {doctors_created}")
    print(f"  Schedules created: {schedules_created}")
    print("=" * 50)


async def main() -> None:
    print()
    print("MEDORA — Booking Flow Seed Script")
    print("=" * 50)
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
