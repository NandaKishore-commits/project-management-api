from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard shape of every paginated list."""
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class MessageOut(BaseModel):
    """For simple answers like {"message": "Member added"}."""
    message: str


def reject_null(value):
    """Used by Update schemas: a field may be left out, but not sent as null."""
    if value is None:
        raise ValueError("This field cannot be null")
    return value