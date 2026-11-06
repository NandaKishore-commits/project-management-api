import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ActivityLog, TaskComment, User
from app.schemas.activity import ActivityOut
from app.schemas.comment import CommentCreate, CommentOut
from app.schemas.common import Page
from app.services.activity import log_activity
from app.services.permissions import get_project_for_view, get_task_for_view
from app.utils.enums import ActivityAction
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

# No prefix here: the paths below start with /tasks or /projects themselves.
router = APIRouter(tags=["Comments & Activity"])


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a task",
    description="Any member of the task's project can comment, and so can an admin.",
)
def add_comment(
    task_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)

    comment = TaskComment(task_id=task.id, user_id=current_user.id, content=data.content)
    db.add(comment)

    # The comment text is not copied into the log, only the fact that it happened
    log_activity(
        db, current_user.id, ActivityAction.COMMENT_ADDED,
        f"Commented on task '{task.title}'",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    db.refresh(comment)

    logger.info("User %s commented on task %s", current_user.email, task.id)
    return comment


@router.get(
    "/tasks/{task_id}/comments",
    response_model=Page[CommentOut],
    summary="List the comments of a task",
    description="Oldest first, like a conversation. Supports pagination.",
)
def list_comments(
    task_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)

    query = (
        select(TaskComment)
        .options(selectinload(TaskComment.user))
        .where(TaskComment.task_id == task.id)
        .order_by(TaskComment.created_at, TaskComment.id)
    )
    return paginate(db, query, page, size)


@router.get(
    "/tasks/{task_id}/activity",
    response_model=Page[ActivityOut],
    summary="Activity history of a task",
    description="Who created, changed, assigned or commented on this task, newest first.",
)
def task_activity(
    task_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)

    query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.user))
        .where(ActivityLog.task_id == task.id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    )
    return paginate(db, query, page, size)


@router.get(
    "/projects/{project_id}/activity",
    response_model=Page[ActivityOut],
    summary="Activity history of a project",
    description="Everything that happened in the project, including its tasks, "
    "newest first. Can be filtered by action.",
)
def project_activity(
    project_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    action: ActivityAction | None = Query(None, description="Show only this kind of event"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_for_view(db, current_user, project_id)

    query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.user))
        .where(ActivityLog.project_id == project.id)
    )
    if action is not None:
        query = query.where(ActivityLog.action == action.value)

    query = query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    return paginate(db, query, page, size)