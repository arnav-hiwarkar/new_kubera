import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_company_user, get_current_auditor
from app.database import get_db
from app.models.company import CompanyUser
from app.models.auditor import Auditor
from app.models.notification import Notification, RecipientType
from app.schemas.notification import NotificationOut

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications_company(
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List notifications for the current company user."""
    result = await db.execute(
        select(Notification)
        .where(
            Notification.recipient_type == RecipientType.company_user,
            Notification.recipient_id == user.id,
        )
        .order_by(Notification.created_at.desc())
        .limit(100)
    )
    return [NotificationOut.model_validate(n) for n in result.scalars().all()]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read_company(
    notification_id: uuid.UUID,
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark a notification as read."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_type == RecipientType.company_user,
            Notification.recipient_id == user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    notification.read_at = datetime.now(timezone.utc)
    db.add(notification)
    await db.flush()
    return NotificationOut.model_validate(notification)
