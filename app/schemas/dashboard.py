from pydantic import BaseModel

from app.schemas.activity import ActivityOut


class DashboardStats(BaseModel):
    total_projects: int
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    overdue_tasks: int
    completion_percent: float
    my_open_tasks: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    recent_activity: list[ActivityOut]