from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    message: str | None
    project_id: int | None
    task_id: int | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread: int


class MarkedReadOut(BaseModel):
    updated: int