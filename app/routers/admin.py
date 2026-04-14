from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminDoctorDetail,
    AdminDoctorsResponse,
    AdminOrgsResponse,
    AdminStatsResponse,
    AdminUserBrief,
    AdminUsersResponse,
    RejectDoctorRequest,
    ToggleActiveRequest,
    UpdateRoleRequest,
)
from app.services.admin_service import (
    delete_doctor_cascade,
    get_admin_stats,
    get_all_doctors_admin,
    get_all_organizations,
    get_all_users,
    get_doctor_detail_admin,
    reject_doctor,
    suspend_doctor,
    toggle_user_active,
    update_user_role,
    verify_doctor,
)

router = APIRouter(prefix="/admin", tags=["Supreme Admin"])

_super_admin = Depends(require_role(UserRole.super_admin))


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminUsersResponse:
    return await get_all_users(db, role=role, is_active=is_active, search=search, skip=skip, limit=limit)


@router.patch("/users/{user_id}/toggle-active")
async def toggle_active(
    user_id: UUID,
    body: ToggleActiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> dict:
    user = await toggle_user_active(db, user_id, body.is_active, current_user.id)
    action = "activated" if body.is_active else "deactivated"
    return {"message": f"User {action}", "user": user}


@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: UUID,
    body: UpdateRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> dict:
    user = await update_user_role(db, user_id, body.role)
    return {"message": "Role updated", "user": user}


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminStatsResponse:
    return await get_admin_stats(db)


@router.get("/organizations", response_model=AdminOrgsResponse)
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminOrgsResponse:
    return await get_all_organizations(db)


# ---------------------------------------------------------------------------
# Doctor verification management
# ---------------------------------------------------------------------------

@router.get(
    "/doctors",
    response_model=AdminDoctorsResponse,
    summary="List self-registered doctors",
    description=(
        "Returns paginated list of self-registered doctors. "
        "Filter by verification_status: pending | verified | rejected | suspended | all."
    ),
)
async def list_doctors(
    verification_status: str = Query(default="all", description="pending | verified | rejected | suspended | all"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminDoctorsResponse:
    return await get_all_doctors_admin(db, verification_status=verification_status, page=page, per_page=per_page)


@router.get(
    "/doctors/{doctor_id}",
    response_model=AdminDoctorDetail,
    summary="Get full doctor details",
)
async def doctor_detail(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminDoctorDetail:
    return await get_doctor_detail_admin(db, doctor_id)


@router.patch(
    "/doctors/{doctor_id}/verify",
    response_model=AdminDoctorDetail,
    summary="Verify a doctor",
    description="Sets doctor.is_verified=True and activates the user account so the doctor can log in.",
)
async def verify_doctor_endpoint(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminDoctorDetail:
    return await verify_doctor(db, doctor_id)


@router.patch(
    "/doctors/{doctor_id}/reject",
    response_model=AdminDoctorDetail,
    summary="Reject a doctor registration",
    description="Sets is_verified=False, keeps user inactive. Optional body: { reason: '...' }.",
)
async def reject_doctor_endpoint(
    doctor_id: UUID,
    body: RejectDoctorRequest = RejectDoctorRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminDoctorDetail:
    return await reject_doctor(db, doctor_id, body.reason)


@router.patch(
    "/doctors/{doctor_id}/suspend",
    response_model=AdminDoctorDetail,
    summary="Suspend a verified doctor",
    description="Deactivates the user account. Doctor remains is_verified=True but cannot log in.",
)
async def suspend_doctor_endpoint(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> AdminDoctorDetail:
    return await suspend_doctor(db, doctor_id)


@router.delete(
    "/doctors/{doctor_id}",
    status_code=204,
    summary="Hard delete a doctor",
    description=(
        "Cascade deletes: reviews → online_consultations → doctor_schedules "
        "→ appointments → doctor → linked user account."
    ),
)
async def delete_doctor_endpoint(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = _super_admin,
) -> None:
    await delete_doctor_cascade(db, doctor_id)
