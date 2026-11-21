from collections import deque
from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_dependency import TaskDependency
from app.models.task_history import TaskHistory
from app.utils.enums import TaskStatus


def _to_history_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def record_history(
    db: Session,
    *,
    task_id: int,
    user_id: int,
    field_name: str,
    old_value: object,
    new_value: object,
) -> None:
    old_str = _to_history_str(old_value)
    new_str = _to_history_str(new_value)
    if old_str == new_str:
        return
    db.add(
        TaskHistory(
            task_id=task_id,
            user_id=user_id,
            field_name=field_name,
            old_value=old_str,
            new_value=new_str,
        )
    )