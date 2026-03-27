import logging
from contextlib import asynccontextmanager
from datetime import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.routers import auth, health

logger = logging.getLogger(__name__)

_DEFAULT_DAYS = range(5)  # Mon–Fri


async def _backfill_doctor_schedules() -> None:
    """Create default Mon-Fri schedules for any doctor that has none."""
    # Import here to avoid circular imports at module load time
    from app.models.doctor import Doctor  # noqa: PLC0415
    from app.models.doctor_schedule import DoctorSchedule  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        # Find doctors with zero schedule records
        subq = (
            select(DoctorSchedule.doctor_id)
            .group_by(DoctorSchedule.doctor_id)
            .having(func.count(DoctorSchedule.id) > 0)
        )
        result = await db.execute(
            select(Doctor)
            .where(Doctor.is_active == True)  # noqa: E712
            .where(Doctor.id.not_in(subq))
        )
        doctors = result.scalars().all()

        if not doctors:
            return

        logger.info(
            "Backfilling default schedules for %d doctor(s) with no schedule records",
            len(doctors),
        )
        for doctor in doctors:
            for dow in _DEFAULT_DAYS:
                db.add(DoctorSchedule(
                    doctor_id=doctor.id,
                    organization_id=doctor.organization_id,
                    day_of_week=dow,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    slot_duration_minutes=30,
                    break_start=time(13, 0),
                    break_end=time(14, 0),
                    is_active=True,
                ))
            logger.info("  → Created Mon-Fri schedules for doctor %s (%s)", doctor.id, doctor.name)

        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _backfill_doctor_schedules()
    yield
from app.routers.organization import router as organization_router
from app.routers.doctor import router as doctor_router
from app.routers.patient import router as patient_router
from app.routers.patient_auth import router as patient_auth_router
from app.routers.appointment import router as appointment_router
from app.routers.reports import router as reports_router
from app.routers.dashboard import router as dashboard_router
from app.routers.medical_history import router as medical_history_router
from app.routers.patient_dashboard import router as patient_dashboard_router
from app.routers.booking import router as booking_router
from app.routers.patient_reports import router as patient_reports_router
from app.routers.admin import router as admin_router
from app.routers.ai import router as ai_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ---------------------------------------------------------------------------
    # Middleware
    # ---------------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------------------
    # Routers
    # ---------------------------------------------------------------------------
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(
        organization_router,
        prefix="/api/v1",
        tags=["Organizations"],
    )
    app.include_router(doctor_router, prefix="/api/v1")
    app.include_router(patient_router, prefix="/api/v1")
    app.include_router(patient_auth_router, prefix="/api/v1")
    app.include_router(appointment_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(medical_history_router, prefix="/api/v1")
    app.include_router(patient_dashboard_router, prefix="/api/v1")
    app.include_router(booking_router, prefix="/api/v1")
    app.include_router(patient_reports_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")

    return app


app = create_app()
