from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskDependency(Base):
    """`task_id` cannot start until `depends_on_id` is COMPLETED."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependency"),
        CheckConstraint("task_id <> depends_on_id", name="ck_task_not_self_dependent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )