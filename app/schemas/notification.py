import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    recipient_type: str
    recipient_id: uuid.UUID
    type: str
    payload: Any | None = None
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
