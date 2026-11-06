from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def paginate(db: Session, query, page: int, size: int) -> dict:
    """Runs a query one page at a time and returns the standard Page shape."""
    # Sorting is not needed for counting, so it is removed to keep the count fast
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = db.scalars(query.offset((page - 1) * size).limit(size)).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": ceil(total / size),
    }