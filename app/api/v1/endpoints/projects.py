import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_manager
from app.db.session import get_db
from app.models import Project, ProjectMember, Task, User
from app.schemas.common import Page
from app.schemas.project import (
    MemberAdd,
    MemberOut,
    ProjectCreate,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
)
from app.services.activity import log_activity
from app.services.permissions import (
    get_project_for_manage,
    get_project_for_view,
    is_admin,
    is_project_member,
)
from app.utils.enums import ActivityAction, ProjectStatus, TaskStatus
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project (admin or project manager)",
    description="The creator is added to the project as its first member.",
)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = Project(**data.model_dump(), created_by=current_user.id)
    project.members.append(ProjectMember(user_id=current_user.id))
    db.add(project)
    db.flush()  # sends the INSERT now, so project.id exists for the log

    log_activity(
        db, current_user.id, ActivityAction.PROJECT_CREATED,
        f"Created project '{project.name}'", project_id=project.id,
    )
    db.commit()
    db.refresh(project)

    logger.info("User %s created project %s", current_user.email, project.id)
    return project


@router.get(
    "",
    response_model=Page[ProjectOut],
    summary="List projects",
    description="Admins see every project. Everyone else sees only the projects "
    "they belong to. Supports pagination, search by name, and a status filter.",
)
def list_projects(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, description="Part of the project name"),
    # "alias" keeps the URL as ?status=... without clashing with the name "status"
    project_status: ProjectStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Project).where(Project.is_deleted.is_(False))

    if not is_admin(current_user):
        my_projects = select(ProjectMember.project_id).where(
            ProjectMember.user_id == current_user.id
        )
        query = query.where(Project.id.in_(my_projects))

    if search and search.strip():
        query = query.where(Project.name.ilike(f"%{search.strip()}%"))
    if project_status is not None:
        query = query.where(Project.status == project_status)

    return paginate(db, query.order_by(Project.id.desc()), page, size)


@router.get("/{project_id}", response_model=ProjectOut, summary="Get project details")
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_project_for_view(db, current_user, project_id)


@router.put(
    "/{project_id}",
    response_model=ProjectOut,
    summary="Update a project",
    description="Send only the fields you want to change.",
)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = get_project_for_manage(db, current_user, project_id)

    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")

    # The schema checks the dates only when BOTH are sent. Here we also cover
    # the case where only one is sent, by comparing it with the saved one.
    new_start = changes.get("start_date", project.start_date)
    new_end = changes.get("end_date", project.end_date)
    if new_end <= new_start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end_date must be after start_date")

    for field, value in changes.items():
        setattr(project, field, value)

    log_activity(
        db, current_user.id, ActivityAction.PROJECT_UPDATED,
        f"Updated project '{project.name}' (changed: {', '.join(changes)})",
        project_id=project.id,
    )
    db.commit()
    db.refresh(project)
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project (soft delete)",
    description="The project and its tasks are hidden, not erased from the database.",
)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = get_project_for_manage(db, current_user, project_id)

    project.is_deleted = True
    # Hide the project's tasks too, so they don't appear in task lists
    db.execute(
        update(Task)
        .where(Task.project_id == project.id, Task.is_deleted.is_(False))
        .values(is_deleted=True)
    )

    log_activity(
        db, current_user.id, ActivityAction.PROJECT_DELETED,
        f"Deleted project '{project.name}'", project_id=project.id,
    )
    db.commit()
    logger.info("User %s deleted project %s", current_user.email, project.id)


@router.get(
    "/{project_id}/members",
    response_model=list[MemberOut],
    summary="List the members of a project",
)
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_project_for_view(db, current_user, project_id)
    return db.scalars(
        select(ProjectMember)
        .options(selectinload(ProjectMember.user))
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.id)
    ).all()


@router.post(
    "/{project_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member to a project",
)
def add_member(
    project_id: int,
    data: MemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = get_project_for_manage(db, current_user, project_id)

    new_user = db.get(User, data.user_id)
    if new_user is None or not new_user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found or inactive")
    if is_project_member(db, new_user.id, project.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already in this project")

    member = ProjectMember(project_id=project.id, user_id=new_user.id)
    db.add(member)
    log_activity(
        db, current_user.id, ActivityAction.MEMBER_ADDED,
        f"Added {new_user.full_name} to the project", project_id=project.id,
    )
    db.commit()
    db.refresh(member)
    return member


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from a project",
    description="The member's open tasks in this project become unassigned.",
)
def remove_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = get_project_for_manage(db, current_user, project_id)

    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This user is not a member of the project")
    if user_id == project.created_by:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove the project creator")

    removed_name = member.user.full_name
    db.delete(member)

    # A task must not stay assigned to someone who left the project
    result = db.execute(
        update(Task)
        .where(
            Task.project_id == project.id,
            Task.assigned_to == user_id,
            Task.is_deleted.is_(False),
        )
        .values(assigned_to=None)
    )

    log_activity(
        db, current_user.id, ActivityAction.MEMBER_REMOVED,
        f"Removed {removed_name} from the project ({result.rowcount} task(s) unassigned)",
        project_id=project.id,
    )
    db.commit()


@router.get(
    "/{project_id}/stats",
    response_model=ProjectStats,
    summary="Task statistics and progress of a project",
    description="progress_percent = completed tasks ÷ total tasks × 100",
)
def project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_for_view(db, current_user, project_id)

    rows = db.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.project_id == project.id, Task.is_deleted.is_(False))
        .group_by(Task.status)
    ).all()

    by_status = {s.value: 0 for s in TaskStatus}  # every status shows up, even with 0
    for task_status, count in rows:
        by_status[task_status.value] = count

    total = sum(by_status.values())
    completed = by_status[TaskStatus.COMPLETED.value]
    progress = round(completed / total * 100, 2) if total else 0.0

    return ProjectStats(
        project_id=project.id,
        total_tasks=total,
        by_status=by_status,
        progress_percent=progress,
    )