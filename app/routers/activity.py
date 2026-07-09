from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_company_user
from app.database import get_db
from app.models.company import CompanyUser
from app.models.activity_log import ActivityLog
from app.schemas.activity import ActivityLogOut

router = APIRouter(prefix="/api/v1/activity-log", tags=["activity-log"])


@router.get("", response_model=list[ActivityLogOut])
async def list_activity_logs(
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
):
    """List activity logs for the current user's company. Optional filters."""
    query = select(ActivityLog).where(
        ActivityLog.company_id == user.company_id
    ).order_by(ActivityLog.created_at.desc())

    if entity_type:
        query = query.where(ActivityLog.entity_type == entity_type)
    if entity_id:
        query = query.where(ActivityLog.entity_id == entity_id)

    query = query.limit(100)
    result = await db.execute(query)
    return [ActivityLogOut.model_validate(r) for r in result.scalars().all()]
