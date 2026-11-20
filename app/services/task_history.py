import enum

from sqlalchemy.orm import Session

from app.models import TaskHistory


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def record_change(db: Session, task_id: int, user_id: int, field: str, old, new) -> None:
    """Adds a history row if the value really changed. Does NOT commit."""
    old_text, new_text = _as_text(old), _as_text(new)
    if old_text == new_text:
        return
    db.add(
        TaskHistory(
            task_id=task_id,
            user_id=user_id,
            field=field,
            old_value=old_text,
            new_value=new_text,
        )
    )