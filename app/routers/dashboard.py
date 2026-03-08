from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import get_dashboard


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _get_org_id(current_user: User) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.get(
    "",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dashboard_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> DashboardResponse:
    org_id = _get_org_id(current_user)
    return await get_dashboard(db, org_id)
