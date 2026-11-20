from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    start_date: date | None = None
    deadline: date | None = None
    estimated_hours: float | None = Field(default=None, gt=0, le=1000)
    project_id: int
    assigned_to: int | None = None
    parent_task_id: int | None = None  # set it to create a subtask

    @field_validator("deadline")
    @classmethod
    def deadline_not_past(cls, v):
        return check_deadline_not_past(v)

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.start_date and self.deadline and self.deadline < self.start_date:
            raise ValueError("deadline cannot be before start_date")
        return self


class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    start_date: date | None = None
    deadline: date | None = None
    estimated_hours: float | None = Field(default=None, gt=0, le=1000)

    @field_validator("deadline")
    @classmethod
    def deadline_not_past(cls, v):
        return check_deadline_not_past(v)

    @field_validator("title", "priority")
    @classmethod
    def no_nulls(cls, v):
        return reject_null(v)

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        # Only when BOTH are sent. If only one is sent, the endpoint
        # compares it with the saved value.
        if self.start_date and self.deadline and self.deadline < self.start_date:
            raise ValueError("deadline cannot be before start_date")
        return self


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskPriorityUpdate(BaseModel):
    priority: TaskPriority


class TaskAssign(BaseModel):
    assigned_to: int
    reason: str | None = Field(default=None, max_length=500)  # optional, used for reassignment


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    start_date: date | None
    deadline: date | None
    estimated_hours: float | None
    project_id: int
    parent_task_id: int | None
    assigned_to: int | None
    created_by: int
    updated_by: int | None
    created_at: datetime
    updated_at: datetime