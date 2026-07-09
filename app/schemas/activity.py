import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class ActivityLogOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    actor_type: str
    actor_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    metadata_: Any | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
