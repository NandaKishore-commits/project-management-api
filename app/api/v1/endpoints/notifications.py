from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Notification, User
from app.schemas.common import Page
from app.schemas.notification import MarkedReadOut, NotificationOut, UnreadCountOut
from app.utils.pagination import paginate

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=Page[NotificationOut],
    summary="List my notifications",
    description="Newest first. Use `is_read=false` to see only the unread ones.",
)
def list_notifications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    is_read: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Notification).where(Notification.user_id == current_user.id)
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)
    query = query.order_by(Notification.created_at.desc(), Notification.id.desc())
    return paginate(db, query, page, size)


@router.get(
    "/unread-count",
    response_model=UnreadCountOut,
    summary="Number of unread notifications",
)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id, Notification.is_read.is_(False)
        )
    )
    return {"unread": count or 0}


@router.patch(
    "/read-all",
    response_model=MarkedReadOut,
    summary="Mark all my notifications as read",
)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = cast(
        CursorResult[Any],
        db.execute(
            update(Notification)
            .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        ),
    )
    db.commit()
    return {"updated": result.rowcount or 0}


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationOut,
    summary="Mark one notification as read",
)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = db.get(Notification, notification_id)
    # Somebody else's notification looks exactly like a missing one
    if notification is None or notification.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return notification