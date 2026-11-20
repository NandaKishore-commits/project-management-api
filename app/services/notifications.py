from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, Task, TaskWatcher, User
from app.utils.enums import NotificationType


def notify(
    db: Session,
    user_id: int,
    type_: NotificationType,
    title: str,
    message: str | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    actor_id: int | None = None,
) -> Notification | None:
    """Adds one notification. Does NOT commit (the endpoint commits).

    Nobody is notified about their own action, so `actor_id` is skipped.
    Day 3 will add the live WebSocket push and the user preferences here.
    """
    if actor_id is not None and user_id == actor_id:
        return None
    notification = Notification(
        user_id=user_id,
        type=type_.value,
        title=title[:200],
        message=message,
        project_id=project_id,
        task_id=task_id,
    )
    db.add(notification)
    return notification


def task_audience(db: Session, task: Task, exclude_user_id: int | None = None) -> list[int]:
    """Active users who care about a task: assignee, creator and watchers."""
    user_ids = set(db.scalars(select(TaskWatcher.user_id).where(TaskWatcher.task_id == task.id)))
    for user_id in (task.assigned_to, task.created_by):
        if user_id is not None:
            user_ids.add(user_id)
    user_ids.discard(exclude_user_id)
    if not user_ids:
        return []
    active = db.scalars(select(User.id).where(User.id.in_(user_ids), User.is_active.is_(True)))
    return sorted(active)


def notify_task_audience(
    db: Session,
    task: Task,
    type_: NotificationType,
    title: str,
    message: str | None = None,
    actor_id: int | None = None,
) -> None:
    for user_id in task_audience(db, task, exclude_user_id=actor_id):
        notify(
            db, user_id, type_, title, message,
            project_id=task.project_id, task_id=task.id,
        )