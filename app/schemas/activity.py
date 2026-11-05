from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserBrief


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    project_id: int | None
    task_id: int | None
    action: str
    details: str | None
    created_at: datetime
    user: UserBrief