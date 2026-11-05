from datetime import date, datetime
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.common import reject_null
from app.schemas.user import UserBrief
from app.utils.enums import ProjectStatus


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=150)
    description: str | None = None
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None

    @field_validator("name", "start_date", "end_date", "status")
    @classmethod
    def no_nulls(cls, v):
        return reject_null(v)

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        # Only checks when BOTH dates are sent. If only one is sent,
        # the endpoint compares it with the date already saved (Step 13).
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    start_date: date
    end_date: date
    status: ProjectStatus
    created_by: int
    created_at: datetime
    updated_at: datetime


class MemberAdd(BaseModel):
    user_id: int


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    joined_at: datetime
    user: UserBrief


class ProjectStats(BaseModel):
    project_id: int
    total_tasks: int
    by_status: dict[str, int]
    progress_percent: float