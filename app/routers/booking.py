from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.booking import (
    BookAppointmentRequest,
    BookAppointmentResponse,
    CityResponse,
    DoctorBrief,
    HospitalBrief,
    SpecializationResponse,
    StateResponse,
    WeekSlotsResponse,
)
from app.services.booking_service import (
    book_appointment,
    get_available_slots,
    get_cities,
    get_doctors,
    get_hospitals,
    get_specializations,
    get_states,
)

router = APIRouter(prefix="/booking", tags=["Appointment Booking"])


class SaveDraftRequest(BaseModel):
    draft: dict[str, Any]


class DraftResponse(BaseModel):
    draft: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Step 1: States
# ---------------------------------------------------------------------------

@router.get("/states", response_model=list[StateResponse])
async def list_states(
    _: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_states(db)


# ---------------------------------------------------------------------------
# Step 2: Cities within a state
# ---------------------------------------------------------------------------

@router.get("/cities", response_model=list[CityResponse])
async def list_cities(
    state: str = Query(..., description="State name, e.g. Maharashtra"),
    _: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_cities(db, state=state)


# ---------------------------------------------------------------------------
# Step 3: Hospitals within a state + city
# ---------------------------------------------------------------------------

@router.get("/hospitals", response_model=list[HospitalBrief])
async def list_hospitals(
    state: str = Query(..., description="State name"),
    city: str = Query(..., description="City name"),
    _: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_hospitals(db, state=state, city=city)


# ---------------------------------------------------------------------------
# Step 4a: Specializations filter for a hospital
# ---------------------------------------------------------------------------

@router.get("/hospitals/{org_id}/specializations", response_model=list[SpecializationResponse])
async def list_specializations(
    org_id: UUID,
    _: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_specializations(db, org_id=org_id)


# ---------------------------------------------------------------------------
# Step 4b: Doctors in a hospital (with optional filters)
# ---------------------------------------------------------------------------

@router.get("/hospitals/{org_id}/doctors", response_model=list[DoctorBrief])
async def list_doctors(
    org_id: UUID,
    specialization: str | None = Query(default=None, description="Filter by specialization"),
    search: str | None = Query(default=None, description="Search by doctor name"),
    _: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_doctors(db, org_id=org_id, specialization=specialization, search=search)


# ---------------------------------------------------------------------------
# Step 5: Available slots for a doctor (7-day window)
# ---------------------------------------------------------------------------

@router.get("/doctors/{doctor_id}/slots", response_model=WeekSlotsResponse)
async def doctor_slots(
    doctor_id: UUID,
    week_start: date | None = Query(
        default=None,
        description="Start date of the 7-day window (YYYY-MM-DD). Defaults to today.",
    ),
    _: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_available_slots(db, doctor_id=doctor_id, week_start=week_start)


# ---------------------------------------------------------------------------
# Step 6: Book appointment
# ---------------------------------------------------------------------------

@router.post("/book", response_model=BookAppointmentResponse, status_code=201)
async def book(
    body: BookAppointmentRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await book_appointment(db, patient_id=current_patient.id, data=body)


# ---------------------------------------------------------------------------
# Draft endpoints
# ---------------------------------------------------------------------------

@router.post("/draft", response_model=dict, status_code=200)
async def save_draft(
    body: SaveDraftRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    current_patient.booking_draft = body.draft
    await db.commit()
    return {"success": True}


@router.get("/draft", response_model=DraftResponse, status_code=200)
async def get_draft(
    current_patient: Patient = Depends(get_current_patient),
):
    return DraftResponse(draft=current_patient.booking_draft)


@router.delete("/draft", response_model=dict, status_code=200)
async def delete_draft(
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    current_patient.booking_draft = None
    await db.commit()
    return {"success": True}
