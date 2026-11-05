from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import reject_null
from app.utils.enums import TaskPriority, TaskStatus


def check_deadline_not_past(value: date | None) -> date | None:
    if value is not None and value < date.today():
        raise ValueError("Deadline cannot be in the past")
    return value


class TaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: date | None = None
    project_id: int
    assigned_to: int | None = None

    @field_validator("deadline")
    @classmethod
    def deadline_not_past(cls, v):
        return check_deadline_not_past(v)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    deadline: date | None = None

    @field_validator("deadline")
    @classmethod
    def deadline_not_past(cls, v):
        return check_deadline_not_past(v)

    @field_validator("title", "priority")
    @classmethod
    def no_nulls(cls, v):
        return reject_null(v)


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskPriorityUpdate(BaseModel):
    priority: TaskPriority


class TaskAssign(BaseModel):
    assigned_to: int


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    deadline: date | None
    project_id: int
    assigned_to: int | None
    created_by: int
    updated_by: int | None
    created_at: datetime
    updated_at: datetime