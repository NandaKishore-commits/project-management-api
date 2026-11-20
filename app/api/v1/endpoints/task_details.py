from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_manager
from app.db.session import get_db
from app.models import (
    ChecklistItem,
    Task,
    TaskChecklist,
    TaskDependency,
    TaskHistory,
    TaskWatcher,
    User,
)
from app.schemas.common import Page
from app.schemas.task import TaskOut
from app.schemas.task_details import (
    ChecklistCreate,
    ChecklistItemCreate,
    ChecklistItemUpdate,
    ChecklistOut,
    DependencyAdd,
    DependencyOut,
    TaskHistoryOut,
    WatcherAdd,
    WatcherOut,
)
from app.services.activity import log_activity
from app.services.permissions import (
    can_manage_project,
    get_task_for_manage,
    get_task_for_view,
    get_task_for_work,
    is_admin,
    is_project_member,
)
from app.services.task_rules import would_create_cycle
from app.utils.enums import ActivityAction, TaskStatus
from app.utils.pagination import paginate

router = APIRouter(prefix="/tasks", tags=["Task Details"])


# =============== subtasks ===============

@router.get(
    "/{task_id}/subtasks",
    response_model=list[TaskOut],
    summary="List the subtasks of a task",
    description="Create a subtask with `POST /tasks` and `parent_task_id`.",
)
def list_subtasks(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)
    return db.scalars(
        select(Task)
        .where(Task.parent_task_id == task.id, Task.is_deleted.is_(False))
        .order_by(Task.id)
    ).all()


# =============== dependencies ===============

def dependency_view(db: Session, task: Task) -> dict:
    depends_on = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
        .where(TaskDependency.task_id == task.id, Task.is_deleted.is_(False))
        .order_by(Task.id)
    ).all()
    blocks = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.task_id == Task.id)
        .where(TaskDependency.depends_on_id == task.id, Task.is_deleted.is_(False))
        .order_by(Task.id)
    ).all()
    return {
        "task_id": task.id,
        "depends_on": depends_on,
        "blocks": blocks,
        "is_blocked": any(t.status != TaskStatus.COMPLETED for t in depends_on),
    }


@router.post(
    "/{task_id}/dependencies",
    response_model=DependencyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Make a task depend on another task (admin or project manager)",
    description="The task cannot leave TODO until the task it depends on is COMPLETED. "
    "Both tasks must be in the same project, and loops are rejected.",
)
def add_dependency(
    task_id: int,
    data: DependencyAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    task = get_task_for_manage(db, current_user, task_id)

    if data.depends_on_id == task.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A task cannot depend on itself")

    prerequisite = db.get(Task, data.depends_on_id)
    if prerequisite is None or prerequisite.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The task to depend on was not found")
    if prerequisite.project_id != task.project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Both tasks must be in the same project")

    exists = db.scalar(
        select(TaskDependency.id).where(
            TaskDependency.task_id == task.id,
            TaskDependency.depends_on_id == prerequisite.id,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "This dependency already exists")
    if would_create_cycle(db, task.id, prerequisite.id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This would create a circular dependency"
        )

    db.add(TaskDependency(task_id=task.id, depends_on_id=prerequisite.id))
    log_activity(
        db, current_user.id, ActivityAction.DEPENDENCY_ADDED,
        f"'{task.title}' now depends on '{prerequisite.title}'",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()
    return dependency_view(db, task)


@router.get(
    "/{task_id}/dependencies",
    response_model=DependencyOut,
    summary="Show what a task depends on, and what waits for it",
)
def get_dependencies(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)
    return dependency_view(db, task)


@router.delete(
    "/{task_id}/dependencies/{depends_on_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a dependency (admin or project manager)",
)
def remove_dependency(
    task_id: int,
    depends_on_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    task = get_task_for_manage(db, current_user, task_id)
    link = db.scalar(
        select(TaskDependency).where(
            TaskDependency.task_id == task.id,
            TaskDependency.depends_on_id == depends_on_id,
        )
    )
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This dependency does not exist")

    db.delete(link)
    log_activity(
        db, current_user.id, ActivityAction.DEPENDENCY_REMOVED,
        f"'{task.title}' no longer depends on task {depends_on_id}",
        project_id=task.project_id, task_id=task.id,
    )
    db.commit()


# =============== checklists ===============
# Read: anyone who can see the task.
# Change: an admin, a manager of the project, or the assignee.

def get_checklist_or_404(db: Session, task_id: int, checklist_id: int) -> TaskChecklist:
    checklist = db.get(TaskChecklist, checklist_id)
    if checklist is None or checklist.task_id != task_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist not found")
    return checklist


def get_item_or_404(db: Session, checklist: TaskChecklist, item_id: int) -> ChecklistItem:
    item = db.get(ChecklistItem, item_id)
    if item is None or item.checklist_id != checklist.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found")
    return item


@router.post(
    "/{task_id}/checklists",
    response_model=ChecklistOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a checklist to a task",
)
def create_checklist(
    task_id: int,
    data: ChecklistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_work(db, current_user, task_id)
    checklist = TaskChecklist(task_id=task.id, title=data.title)
    db.add(checklist)
    db.commit()
    db.refresh(checklist)
    return checklist


@router.get(
    "/{task_id}/checklists",
    response_model=list[ChecklistOut],
    summary="List the checklists of a task, with their progress",
)
def list_checklists(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)
    return db.scalars(
        select(TaskChecklist)
        .options(selectinload(TaskChecklist.items))
        .where(TaskChecklist.task_id == task.id)
        .order_by(TaskChecklist.id)
    ).all()


@router.delete(
    "/{task_id}/checklists/{checklist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a checklist and its items",
)
def delete_checklist(
    task_id: int,
    checklist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_work(db, current_user, task_id)
    checklist = get_checklist_or_404(db, task.id, checklist_id)
    db.delete(checklist)
    db.commit()


@router.post(
    "/{task_id}/checklists/{checklist_id}/items",
    response_model=ChecklistOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to a checklist",
    description="Returns the whole checklist, including its progress.",
)
def add_checklist_item(
    task_id: int,
    checklist_id: int,
    data: ChecklistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_work(db, current_user, task_id)
    checklist = get_checklist_or_404(db, task.id, checklist_id)
    db.add(ChecklistItem(checklist_id=checklist.id, content=data.content))
    db.commit()
    db.refresh(checklist)
    return checklist


@router.patch(
    "/{task_id}/checklists/{checklist_id}/items/{item_id}",
    response_model=ChecklistOut,
    summary="Tick or untick a checklist item",
    description="Returns the whole checklist, including its progress.",
)
def update_checklist_item(
    task_id: int,
    checklist_id: int,
    item_id: int,
    data: ChecklistItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_work(db, current_user, task_id)
    checklist = get_checklist_or_404(db, task.id, checklist_id)
    item = get_item_or_404(db, checklist, item_id)
    item.is_done = data.is_done
    db.commit()
    db.refresh(checklist)
    return checklist


@router.delete(
    "/{task_id}/checklists/{checklist_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a checklist item",
)
def delete_checklist_item(
    task_id: int,
    checklist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_work(db, current_user, task_id)
    checklist = get_checklist_or_404(db, task.id, checklist_id)
    item = get_item_or_404(db, checklist, item_id)
    db.delete(item)
    db.commit()


# =============== watchers ===============

@router.post(
    "/{task_id}/watchers",
    response_model=WatcherOut,
    status_code=status.HTTP_201_CREATED,
    summary="Watch a task",
    description="Watchers are notified when the task changes. You can add yourself. "
    "Only an admin or a project manager can add other people, who must be project members.",
)
def add_watcher(
    task_id: int,
    data: WatcherAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)

    if data.user_id != current_user.id and not can_manage_project(db, current_user, task.project_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only a manager can add other people as watchers"
        )

    target = db.get(User, data.user_id)
    if (
        target is None
        or not target.is_active
        or not (is_admin(target) or is_project_member(db, target.id, task.project_id))
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "A watcher must be an active member of the project"
        )

    already = db.scalar(
        select(TaskWatcher.id).where(
            TaskWatcher.task_id == task.id, TaskWatcher.user_id == target.id
        )
    )
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already watching this task")

    watcher = TaskWatcher(task_id=task.id, user_id=target.id)
    db.add(watcher)
    db.commit()
    db.refresh(watcher)
    return watcher


@router.get(
    "/{task_id}/watchers",
    response_model=list[WatcherOut],
    summary="List the watchers of a task",
)
def list_watchers(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)
    return db.scalars(
        select(TaskWatcher)
        .options(selectinload(TaskWatcher.user))
        .where(TaskWatcher.task_id == task.id)
        .order_by(TaskWatcher.id)
    ).all()


@router.delete(
    "/{task_id}/watchers/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop watching a task",
    description="You can remove yourself. A manager can remove anyone.",
)
def remove_watcher(
    task_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)
    if user_id != current_user.id and not can_manage_project(db, current_user, task.project_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only a manager can remove other watchers"
        )
    watcher = db.scalar(
        select(TaskWatcher).where(TaskWatcher.task_id == task.id, TaskWatcher.user_id == user_id)
    )
    if watcher is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This user is not watching the task")
    db.delete(watcher)
    db.commit()


# =============== history ===============

@router.get(
    "/{task_id}/history",
    response_model=Page[TaskHistoryOut],
    summary="Full update history of a task",
    description="Every changed field with its old and new value and who changed it, newest first.",
)
def task_history(
    task_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_for_view(db, current_user, task_id)
    query = (
        select(TaskHistory)
        .options(selectinload(TaskHistory.user))
        .where(TaskHistory.task_id == task.id)
        .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())
    )
    return paginate(db, query, page, size)