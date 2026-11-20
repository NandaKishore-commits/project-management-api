from collections import deque
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_dependency import TaskDependency
from app.models.task_history import TaskHistory
from app.utils.enums import TaskStatus


def record_history(
    db: Session,
    *,
    task_id: int,
    user_id: int,
    field_name: str,
    old_value: object,
    new_value: object,
) -> None:
    old_str = str(old_value.value if hasattr(old_value, "value") else old_value) if old_value is not None else None
    new_str = str(new_value.value if hasattr(new_value, "value") else new_value) if new_value is not None else None
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


def would_create_cycle(db: Session, task_id: int, depends_on_id: int) -> bool:
    """Return True if adding `task_id -> depends_on_id` creates a cycle."""
    if task_id == depends_on_id:
        return True

    visited: set[int] = set()
    queue = deque([depends_on_id])

    while queue:
        current = queue.popleft()
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        parents = (
            db.query(TaskDependency.depends_on_id)
            .filter(TaskDependency.task_id == current)
            .all()
        )
        for (parent_id,) in parents:
            queue.append(parent_id)

    return False


def ensure_dependencies_completed(db: Session, task_id: int) -> None:
    """Raise 400 if any prerequisite task is not COMPLETED."""
    incomplete = (
        db.query(Task.id, Task.title, Task.status)
        .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
        .filter(
            TaskDependency.task_id == task_id,
            Task.is_deleted.is_(False),
            Task.status != TaskStatus.COMPLETED,
        )
        .all()
    )
    if incomplete:
        blocking_titles = ", ".join(f"#{t.id} ({t.title})" for t in incomplete)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete task while dependencies are unfinished: {blocking_titles}",
        )