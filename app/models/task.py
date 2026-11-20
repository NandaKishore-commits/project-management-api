from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.utils.enums import TaskPriority, TaskStatus


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.TODO, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.MEDIUM, index=True
    )
    deadline: Mapped[date | None] = mapped_column(Date)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_deleted: Mapped[bool] = mapped_column(default=False)
        # --- Phase 2 ---
    start_date: Mapped[date | None] = mapped_column(Date)
    estimated_hours: Mapped[float | None] = mapped_column(Numeric(6, 2, asdecimal=False))
    parent_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", name="fk_tasks_parent_task_id"), index=True
    )  # a subtask points to its parent task

    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assigned_to])
    comments = relationship(
        "TaskComment", back_populates="task", cascade="all, delete-orphan"
    )