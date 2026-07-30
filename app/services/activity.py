"""Append-only activity log writer.

Extracted from app/routers/docvault.py, where the original helper lived and
hardcoded ActorType.company_user. Callers commit.
"""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog, ActorType


async def log_activity(
    db: AsyncSession,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    metadata_: Optional[dict] = None,
    actor_type: ActorType = ActorType.company_user,
) -> None:
    """Queue an activity row. Does not commit — the caller's transaction owns it,
    so a failed operation cannot leave an orphan audit entry."""
    db.add(
        ActivityLog(
            company_id=company_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_=metadata_,
        )
    )
