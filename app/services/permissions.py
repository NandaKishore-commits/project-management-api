from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, ProjectMember, User
from app.utils.enums import RoleName


def is_admin(user: User) -> bool:
    return user.role.name == RoleName.ADMIN.value


def is_project_member(db: Session, user_id: int, project_id: int) -> bool:
    found = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return found is not None


def can_view_project(db: Session, user: User, project_id: int) -> bool:
    """Admin sees everything. Everyone else needs to be a member."""
    return is_admin(user) or is_project_member(db, user.id, project_id)


def can_manage_project(db: Session, user: User, project_id: int) -> bool:
    """Admin manages everything. A project manager manages projects they belong to."""
    if is_admin(user):
        return True
    return user.role.name == RoleName.PROJECT_MANAGER.value and is_project_member(
        db, user.id, project_id
    )


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def get_project_for_view(db: Session, user: User, project_id: int) -> Project:
    """Loads the project, or raises 404 (missing) / 403 (not a member)."""
    project = get_project_or_404(db, project_id)
    if not can_view_project(db, user, project.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this project")
    return project


def get_project_for_manage(db: Session, user: User, project_id: int) -> Project:
    """Same as above, but the user must be allowed to change the project."""
    project = get_project_or_404(db, project_id)
    if not can_manage_project(db, user, project.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can manage only projects you belong to"
        )
    return project