import logging
import os
from contextlib import asynccontextmanager
from datetime import time
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

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
    # Log only the DB hostname — never the password or full URL.
    _parsed = urlparse(settings.DIRECT_URL or settings.DATABASE_URL)
    logger.info("Database host: %s", _parsed.hostname)

    # Backfill is best-effort: a slow or unreachable DB must never prevent the
    # app from binding to its port (Render fails deploys on "no open port").
    try:
        await _backfill_doctor_schedules()
    except Exception as e:
        logger.error("Startup backfill skipped: %s", e, exc_info=True)

    # Log all registered routes at startup to help verify registration.
    for route in app.routes:
        if hasattr(route, "methods"):
            methods = ",".join(sorted(route.methods))
            logger.info("ROUTE  %-30s  %s", methods, route.path)
    yield
from app.routers.organization import router as organization_router
from app.routers.users import router as users_router
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
from app.routers.doctor_auth import router as doctor_auth_router
from app.routers.doctor_dashboard import router as doctor_dashboard_router
from app.routers.doctors_public import router as doctors_public_router
from app.routers.notifications import router as notifications_router
from app.routers.patient_report_alias import router as patient_report_alias_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ---------------------------------------------------------------------------
    # Health check at root — must not be behind any prefix or auth.
    # Render's health check hits /health; this endpoint never touches the DB.
    # ---------------------------------------------------------------------------
    @app.get("/health", include_in_schema=False)
    async def root_health_check():
        return {"status": "ok"}

    @app.get("/health/db", include_in_schema=False)
    async def db_health_check():
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "database": "unreachable", "detail": str(e)},
            )

    # ---------------------------------------------------------------------------
    # Middleware
    # ---------------------------------------------------------------------------
    _cors_env = os.getenv("CORS_ORIGINS", "").strip()
    _cors_origins = (
        [o.strip() for o in _cors_env.split(",") if o.strip()]
        if _cors_env
        else [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8080",
            "http://localhost:8081",
            "http://localhost:8082",
            "http://localhost:8083",
            "http://localhost:8084",
            "http://localhost:8085",
            "http://localhost:8090",
            "http://localhost:19006",
            "http://127.0.0.1:3000",
            "https://medorahealth.in",
            "https://www.medorahealth.in",
            "https://medora-frontend.vercel.app",
            "https://medora-web.vercel.app",
            "https://medora.vercel.app",
        ]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=r"https?://localhost:\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------------------
    # Routers
    # ---------------------------------------------------------------------------
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(
        organization_router,
        prefix="/api/v1",
        tags=["Organizations"],
    )
    # doctors_public MUST be included before doctor_router: static paths /search and
    # /specialties must be registered before the /{doctor_id} pattern or FastAPI
    # will swallow them as doctor_id="search" / doctor_id="specialties".
    app.include_router(doctors_public_router, prefix="/api/v1/doctors", tags=["Doctors Public"])
    app.include_router(doctor_router, prefix="/api/v1")
    app.include_router(patient_router, prefix="/api/v1")
    app.include_router(patient_auth_router, prefix="/api/v1")
    app.include_router(appointment_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(patient_report_alias_router, prefix="/api/v1/reports", tags=["Patient Reports"])
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(medical_history_router, prefix="/api/v1")
    app.include_router(patient_dashboard_router, prefix="/api/v1")
    app.include_router(booking_router, prefix="/api/v1")
    app.include_router(patient_reports_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(doctor_auth_router, prefix="/api/v1/doctor", tags=["Doctor Auth"])
    app.include_router(doctor_dashboard_router, prefix="/api/v1/doctor", tags=["Doctor Dashboard"])
    app.include_router(notifications_router, prefix="/api/v1")

    return app


app = create_app()
