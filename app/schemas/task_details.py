from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.user import UserBrief
from app.utils.enums import TaskStatus


class TaskBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: TaskStatus


# ---------- dependencies ----------

class DependencyAdd(BaseModel):
    depends_on_id: int  # the task that must be completed first


class DependencyOut(BaseModel):
    task_id: int
    depends_on: list[TaskBrief]  # must be finished before this task can start
    blocks: list[TaskBrief]  # tasks waiting for this one
    is_blocked: bool


# ---------- checklists ----------

class ChecklistCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=150)


class ChecklistItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=255)


class ChecklistItemUpdate(BaseModel):
    is_done: bool


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    is_done: bool


class ChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    title: str
    items: list[ChecklistItemOut]

    @computed_field
    @property
    def progress_percent(self) -> float:
        if not self.items:
            return 0.0
        done = sum(1 for item in self.items if item.is_done)
        return round(done / len(self.items) * 100, 2)


# ---------- watchers ----------

class WatcherAdd(BaseModel):
    user_id: int


class WatcherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    user: UserBrief


# ---------- history ----------

class TaskHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    field: str
    old_value: str | None
    new_value: str | None
    created_at: datetime
    user: UserBrief