from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskDependency
from app.utils.enums import TaskStatus


def open_prerequisites(db: Session, task_id: int) -> list[Task]:
    """Tasks that must be finished before `task_id` can start, and are not finished yet."""
    return list(
        db.scalars(
            select(Task)
            .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
            .where(
                TaskDependency.task_id == task_id,
                Task.is_deleted.is_(False),
                Task.status != TaskStatus.COMPLETED,
            )
            .order_by(Task.id)
        )
    )


def open_subtasks(db: Session, task_id: int) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(
                Task.parent_task_id == task_id,
                Task.is_deleted.is_(False),
                Task.status != TaskStatus.COMPLETED,
            )
            .order_by(Task.id)
        )
    )


def would_create_cycle(db: Session, task_id: int, depends_on_id: int) -> bool:
    """True if "task_id depends on depends_on_id" would close a loop.

    Walk through the prerequisites of `depends_on_id`. If we ever reach
    `task_id`, the new link would create a loop (A needs B, B needs A).
    """
    seen: set[int] = set()
    stack = [depends_on_id]
    while stack:
        current = stack.pop()
        if current == task_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(
            db.scalars(
                select(TaskDependency.depends_on_id).where(TaskDependency.task_id == current)
            )
        )
    return False


def titles_of(tasks: list[Task]) -> str:
    return ", ".join(f"'{t.title}'" for t in tasks)