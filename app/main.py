from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, health
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


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
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

    return app


app = create_app()
