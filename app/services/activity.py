from sqlalchemy.orm import Session

from app.models import ActivityLog
from app.utils.enums import ActivityAction


def log_activity(
    db: Session,
    user_id: int,
    action: ActivityAction,
    details: str | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
) -> None:
    """Adds one row to activity_logs.

    It does NOT commit. The endpoint commits, so the change and its log
    entry are saved together, or neither is saved.
    """
    db.add(
        ActivityLog(
            user_id=user_id,
            action=action.value,
            details=details,
            project_id=project_id,
            task_id=task_id,
        )
    )