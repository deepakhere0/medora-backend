from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminOrgsResponse,
    AdminStatsResponse,
    AdminUserBrief,
    AdminUsersResponse,
    ToggleActiveRequest,
    UpdateRoleRequest,
)
from app.services.admin_service import (
    get_admin_stats,
    get_all_organizations,
    get_all_users,
    toggle_user_active,
    update_user_role,
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
