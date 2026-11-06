import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_manager
from app.db.session import get_db
from app.models import Project, ProjectMember, Task, User
from app.schemas.common import Page
from app.schemas.task import (
    TaskAssign,
    TaskCreate,
    TaskOut,
    TaskPriorityUpdate,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.activity import log_activity
from app.services.permissions import (
    can_manage_project,
    get_project_for_manage,
    get_task_for_manage,
    get_task_for_view,
    get_task_or_404,
    is_admin,
    is_project_member,
)
from app.utils.enums import ActivityAction, TaskPriority, TaskStatus
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ---------- helpers ----------

def check_deadline_in_project(deadline: date | None, project: Project) -> None:
    if deadline is not None and deadline > project.end_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Deadline cannot be after the project end date ({project.end_date})",
        )


def get_assignable_user(db: Session, project_id: int, user_id: int) -> User:
    """The assignee must exist, be active, and belong to the project."""
    user = db.get(User, user_id)
    if user is None or not user.is_active or not is_project_member(db, user_id, project_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Assigned user must be an active member of this project",
        )
    return user


def apply_filters(query, task_status, priority, search):
    if task_status is not None:
        query = query.where(Task.status == task_status)
    if priority is not None:
        query = query.where(Task.priority == priority)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(or_(Task.title.ilike(term), Task.description.ilike(term)))
    return query


def apply_sort(query, sort_by: str, order: str):
    column = Task.deadline if sort_by == "deadline" else Task.created_at
    direction = column.asc() if order == "asc" else column.desc()
    # Tasks without a deadline always go last. Task.id keeps the page order stable.
    return query.order_by(direction.nulls_last(), Task.id)


# ---------- create ----------

@router.post(
    "",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task (admin or project manager)",
    description="New tasks always start as TODO. The assignee must be a member of the project.",
)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = get_project_for_manage(db, current_user, data.project_id)
    check_deadline_in_project(data.deadline, project)

    assignee = None
    if data.assigned_to is not None:
        assignee = get_assignable_user(db, project.id, data.assigned_to)

    task = Task(**data.model_dump(), created_by=current_user.id, updated_by=current_user.id)
    db.add(task)
    db.flush()  # gives task.id for the log

    log_activity(
        db, current_user.id, ActivityAction.TASK_CREATED,
        f"Created task '{task.title}'", project_id=project.id, task_id=task.id,
    )
    if assignee:
        log_activity(
            db, current_user.id, ActivityAction.TASK_ASSIGNED,
            f"Assigned to {assignee.full_name}", project_id=project.id, task_id=task.id,
        )
    db.commit()
    db.refresh(task)

    logger.info("User %s created task %s", current_user.email, task.id)
    return task


# ---------- lists ----------
# IMPORTANT: "/my" must be written BEFORE "/{task_id}".
# Otherwise FastAPI reads the word "my" as a task id and returns 422.

@router.get(
    "/my",
    response_model=Page[TaskOut],
    summary="Tasks assigned to the logged-in user",
    description="Sorted by nearest deadline first. Supports the same filters as the main list.",
)
def my_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    task_status: TaskStatus | None = Query(None, alias="status"),
    priority: TaskPriority | None = None,
    search: str | None = None,
    sort_by: Literal["deadline", "created_at"] = "deadline",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Task).where(
        Task.assigned_to == current_user.id, Task.is_deleted.is_(False)
    )
    query = apply_filters(query, task_status, priority, search)
    return paginate(db, apply_sort(query, sort_by, order), page, size)


@router.get(
    "",
    response_model=Page[TaskOut],
    summary="List tasks with filters, search, sorting and pagination",
    description="Admins see every task. Everyone else sees the tasks of the projects they belong to.",
)
def list_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    task_status: TaskStatus | None = Query(None, alias="status"),
    priority: TaskPriority | None = None,
    project_id: int | None = None,
    assigned_to: int | None = None,
    search: str | None = Query(None, description="Part of the title or description"),
    sort_by: Literal["deadline", "created_at"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Task).where(Task.is_deleted.is_(False))

    if not is_admin(current_user):
        my_projects = select(ProjectMember.project_id).where(
            ProjectMember.user_id == current_user.id
        )
        query = query.where(Task.project_id.in_(my_projects))

    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if assigned_to is not None:
        query = query.where(Task.assigned_to == assigned_to)

    query = apply_filters(query, task_status, priority, search)
    return paginate(db, apply_sort(query, sort_by, order), page, size)


# ---------- one task ----------

@router.get("/{task_id}", response_model=TaskOut, summary="Get task details")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_task_for_view(db, current_user, task_id)


@router.put(
    "/{task_id}",
    response_model=TaskOut,
    summary="Update a task (admin or project manager)",
    description="Send only the fields you want to change. Status, priority and assignee "
    "have their own endpoints.",
)
def update_task(
    task_id: int,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    task = get_task_for_manage(db, current_user, task_id)

    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")

    if "deadline" in changes:
        check_deadline_in_project(changes["deadline"], task.project)

    for field, value in changes.items():
        setattr(task, field, value)
    task.updated_by = current_user.id

    log_activity(
        db, current_user.id, ActivityAction.TASK_UPDATED,
        f"Updated task '{task.title}' (changed: {', '.join(changes)})",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch(
    "/{task_id}/status",
    response_model=TaskOut,
    summary="Change the status of a task",
    description="Admins and project managers (of the project) can change any task. "
    "A team member can change only the tasks assigned to them.",
)
def update_task_status(
    task_id: int,
    data: TaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_or_404(db, task_id)

    allowed = (
        can_manage_project(db, current_user, task.project_id)
        or task.assigned_to == current_user.id
    )
    if not allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can change the status only of tasks assigned to you"
        )
    if task.status == data.status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Task is already {data.status.value}")

    old_status = task.status
    task.status = data.status
    task.updated_by = current_user.id

    log_activity(
        db, current_user.id, ActivityAction.STATUS_CHANGED,
        f"{old_status.value} -> {data.status.value}",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch(
    "/{task_id}/priority",
    response_model=TaskOut,
    summary="Change the priority of a task (admin or project manager)",
)
def update_task_priority(
    task_id: int,
    data: TaskPriorityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    task = get_task_for_manage(db, current_user, task_id)

    if task.priority == data.priority:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Priority is already {data.priority.value}")

    old_priority = task.priority
    task.priority = data.priority
    task.updated_by = current_user.id

    log_activity(
        db, current_user.id, ActivityAction.PRIORITY_CHANGED,
        f"{old_priority.value} -> {data.priority.value}",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch(
    "/{task_id}/assign",
    response_model=TaskOut,
    summary="Assign a task to a project member (admin or project manager)",
)
def assign_task(
    task_id: int,
    data: TaskAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    task = get_task_for_manage(db, current_user, task_id)
    assignee = get_assignable_user(db, task.project_id, data.assigned_to)

    if task.assigned_to == assignee.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Task is already assigned to this user")

    task.assigned_to = assignee.id
    task.updated_by = current_user.id

    log_activity(
        db, current_user.id, ActivityAction.TASK_ASSIGNED,
        f"Assigned to {assignee.full_name}",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task (soft delete)",
)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    task = get_task_for_manage(db, current_user, task_id)

    task.is_deleted = True
    task.updated_by = current_user.id
    log_activity(
        db, current_user.id, ActivityAction.TASK_DELETED,
        f"Deleted task '{task.title}'", project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    logger.info("User %s deleted task %s", current_user.email, task.id)