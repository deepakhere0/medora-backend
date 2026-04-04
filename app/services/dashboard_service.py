from calendar import monthrange
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import distinct, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor, DoctorStatus
from app.models.patient import Patient
from app.models.patient_organization import PatientOrganization
from app.schemas.dashboard import (
    AppointmentStats,
    DashboardResponse,
    DoctorStats,
    PatientStats,
    WeeklyTrend,
)


async def _get_patient_stats(
    db: AsyncSession,
    org_id: UUID,
) -> PatientStats:
    today = date.today()
    first_day_this_month = today.replace(day=1)
    first_day_last_month = (
        first_day_this_month - timedelta(days=1)
    ).replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)

    # Patients linked to this org via direct organization_id (walk-in) OR
    # via the patient_organizations junction table (booking portal).
    # Using OR + subquery ensures existing data is counted correctly without migration.
    linked_via_junction = (
        select(PatientOrganization.patient_id).where(
            PatientOrganization.organization_id == org_id,
            PatientOrganization.is_active.is_(True),
        )
    )
    org_filter = or_(
        Patient.organization_id == org_id,
        Patient.id.in_(linked_via_junction),
    )

    # total active patients in org — distinct avoids double-counting patients
    # that appear in BOTH the direct organization_id column and the junction table
    active_result = await db.execute(
        select(func.count(distinct(Patient.id))).where(
            org_filter,
            Patient.is_active.is_(True),
        )
    )
    total_active: int = active_result.scalar_one() or 0

    # patients created last calendar month
    last_month_result = await db.execute(
        select(func.count(distinct(Patient.id))).where(
            org_filter,
            Patient.is_active.is_(True),
            Patient.created_at >= first_day_last_month,
            Patient.created_at <= last_day_last_month,
        )
    )
    total_last_month: int = last_month_result.scalar_one() or 0

    if total_last_month == 0:
        growth: float = 0.0
    else:
        growth = round(
            (total_active - total_last_month) / total_last_month * 100, 1
        )

    return PatientStats(
        total_active=total_active,
        total_last_month=total_last_month,
        growth_percentage=growth,
    )


async def _get_doctor_stats(
    db: AsyncSession,
    org_id: UUID,
) -> DoctorStats:
    # total active doctors in org
    total_result = await db.execute(
        select(func.count(Doctor.id)).where(
            Doctor.organization_id == org_id,
            Doctor.is_active == True,
        )
    )
    total_doctors: int = total_result.scalar_one()

    # doctors currently on duty
    on_duty_result = await db.execute(
        select(func.count(Doctor.id)).where(
            Doctor.organization_id == org_id,
            Doctor.is_active == True,
            Doctor.status == DoctorStatus.on_duty,
        )
    )
    on_duty_count: int = on_duty_result.scalar_one()

    return DoctorStats(
        total_doctors=total_doctors,
        on_duty_count=on_duty_count,
    )


async def _get_appointment_stats(
    db: AsyncSession,
    org_id: UUID,
) -> AppointmentStats:
    today = date.today()

    async def _count_by_status(appt_status: AppointmentStatus) -> int:
        result = await db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.organization_id == org_id,
                Appointment.appointment_date == today,
                Appointment.is_active == True,
                Appointment.status == appt_status,
            )
        )
        return result.scalar_one()

    scheduled_count: int = await _count_by_status(AppointmentStatus.scheduled)
    confirmed_count: int = await _count_by_status(AppointmentStatus.confirmed)
    completed_count: int = await _count_by_status(AppointmentStatus.completed)
    cancelled_count: int = await _count_by_status(AppointmentStatus.cancelled)

    total_today: int = (
        scheduled_count + confirmed_count + completed_count + cancelled_count
    )

    return AppointmentStats(
        total_today=total_today,
        scheduled_count=scheduled_count,
        confirmed_count=confirmed_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
    )


async def _get_weekly_trend(
    db: AsyncSession,
    org_id: UUID,
) -> list[WeeklyTrend]:
    today = date.today()
    year = today.year
    month = today.month
    days_in_month = monthrange(year, month)[1]

    weeks: list[tuple[int, int, int]] = [
        (1,  1,  7),
        (2,  8,  14),
        (3,  15, 21),
        (4,  22, days_in_month),
    ]

    trend: list[WeeklyTrend] = []
    month_name: str = today.strftime("%b")

    for week_num, start_day, end_day in weeks:
        week_start = date(year, month, start_day)
        week_end   = date(year, month, end_day)

        result = await db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.organization_id == org_id,
                Appointment.is_active == True,
                Appointment.appointment_date >= week_start,
                Appointment.appointment_date <= week_end,
            )
        )
        count: int = result.scalar_one()
        week_label = f"Week {week_num} ({month_name} {start_day}-{end_day})"
        trend.append(WeeklyTrend(week_label=week_label, count=count))

    return trend


async def get_dashboard(
    db: AsyncSession,
    org_id: UUID,
) -> DashboardResponse:
    patient_stats     = await _get_patient_stats(db, org_id)
    doctor_stats      = await _get_doctor_stats(db, org_id)
    appointment_stats = await _get_appointment_stats(db, org_id)
    weekly_trend      = await _get_weekly_trend(db, org_id)

    return DashboardResponse(
        patients=patient_stats,
        doctors=doctor_stats,
        appointments=appointment_stats,
        trend=weekly_trend,
    )
