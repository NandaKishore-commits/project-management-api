from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ActivityLog, Project, ProjectMember, Task, User
from app.schemas.dashboard import DashboardStats
from app.services.permissions import is_admin
from app.utils.enums import TaskPriority, TaskStatus

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

RECENT_ACTIVITY_LIMIT = 10


def visible_project_ids(user: User) -> Select:
    """ids of the live projects this user is allowed to see."""
    query = select(Project.id).where(Project.is_deleted.is_(False))
    if not is_admin(user):
        my_projects = select(ProjectMember.project_id).where(
            ProjectMember.user_id == user.id
        )
        query = query.where(Project.id.in_(my_projects))
    return query


@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Dashboard statistics",
    description="Totals, task counts by status and priority, completion percentage, "
    "overdue tasks and the 10 most recent activities. Admins see everything. "
    "Everyone else sees only the projects they belong to.",
)
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project_ids = visible_project_ids(current_user)

    total_projects = db.scalar(select(func.count()).select_from(project_ids.subquery())) or 0

    # Every task query below uses the same scope: live tasks of visible projects
    task_scope = (Task.is_deleted.is_(False), Task.project_id.in_(project_ids))

    # --- tasks by status ---
    status_rows = db.execute(
        select(Task.status, func.count(Task.id)).where(*task_scope).group_by(Task.status)
    ).all()
    by_status = {s.value: 0 for s in TaskStatus}  # every status appears, even with 0
    for task_status, count in status_rows:
        by_status[task_status.value] = count

    # --- tasks by priority ---
    priority_rows = db.execute(
        select(Task.priority, func.count(Task.id)).where(*task_scope).group_by(Task.priority)
    ).all()
    by_priority = {p.value: 0 for p in TaskPriority}
    for task_priority, count in priority_rows:
        by_priority[task_priority.value] = count

    total_tasks = sum(by_status.values())
    completed = by_status[TaskStatus.COMPLETED.value]
    in_progress = by_status[TaskStatus.IN_PROGRESS.value] + by_status[TaskStatus.REVIEW.value]
    pending = by_status[TaskStatus.TODO.value]
    completion = round(completed / total_tasks * 100, 2) if total_tasks else 0.0

    # --- overdue: the deadline has passed and the work is not finished ---
    overdue = db.scalar(
        select(func.count(Task.id)).where(
            *task_scope,
            Task.deadline < date.today(),
            Task.status != TaskStatus.COMPLETED,
        )
    ) or 0

    # --- tasks assigned to me that are still open ---
    my_open = db.scalar(
        select(func.count(Task.id)).where(
            *task_scope,
            Task.assigned_to == current_user.id,
            Task.status != TaskStatus.COMPLETED,
        )
    ) or 0

    # --- recent activity ---
    activity_query = select(ActivityLog).options(selectinload(ActivityLog.user))
    if not is_admin(current_user):
        activity_query = activity_query.where(ActivityLog.project_id.in_(project_ids))
    recent_activity = db.scalars(
        activity_query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
    ).all()

    return {
        "total_projects": total_projects,
        "total_tasks": total_tasks,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "pending_tasks": pending,
        "overdue_tasks": overdue,
        "completion_percent": completion,
        "my_open_tasks": my_open,
        "by_status": by_status,
        "by_priority": by_priority,
        "recent_activity": recent_activity,
    }