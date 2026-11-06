import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_admin, require_manager
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Role, User
from app.schemas.common import Page
from app.schemas.user import (
    UserAdminCreate,
    UserOut,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.utils.enums import RoleName
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def get_role(db: Session, role_name: RoleName) -> Role:
    role = db.scalar(select(Role).where(Role.name == role_name.value))
    if role is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Roles are not set up. Run: python -m scripts.seed",
        )
    return role


@router.get(
    "",
    response_model=Page[UserOut],
    summary="List users",
    description="Admin and project manager only. Supports pagination, search "
    "(name or email), and filters by active status and role.",
)
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, description="Part of a name or an email"),
    is_active: bool | None = None,
    role: RoleName | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    query = select(User).options(selectinload(User.role))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if role is not None:
        query = query.join(Role).where(Role.name == role.value)

    return paginate(db, query.order_by(User.id), page, size)


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin only)",
)
def create_user(
    data: UserAdminCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    role = get_role(db, data.role)
    user = User(
        full_name=data.full_name,
        email=email,
        hashed_password=hash_password(data.password),
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("Admin %s created user %s with role %s", admin.email, user.email, role.name)
    return user


@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get one user (admin only)",
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return get_user_or_404(db, user_id)


@router.put(
    "/{user_id}",
    response_model=UserOut,
    summary="Update a profile",
    description="An admin can update anyone. Other users can update only themselves.",
)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Permission is checked BEFORE looking up the user, so a normal user
    # cannot find out which user ids exist.
    is_admin = current_user.role.name == RoleName.ADMIN.value
    if not is_admin and current_user.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can update only your own profile")

    user = get_user_or_404(db, user_id)

    # Only the fields the client really sent
    changes = data.model_dump(exclude_unset=True)

    if "email" in changes:
        changes["email"] = changes["email"].lower()
        taken = db.scalar(
            select(User).where(User.email == changes["email"], User.id != user_id)
        )
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    for field, value in changes.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.patch(
    "/{user_id}/status",
    response_model=UserOut,
    summary="Activate or deactivate a user (admin only)",
)
def set_user_status(
    user_id: int,
    data: UserStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)

    if user.id == admin.id and not data.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account")

    user.is_active = data.is_active
    db.commit()
    db.refresh(user)

    logger.info("Admin %s set is_active=%s for user %s", admin.email, user.is_active, user.email)
    return user


@router.patch(
    "/{user_id}/role",
    response_model=UserOut,
    summary="Assign a role (admin only)",
)
def set_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = get_user_or_404(db, user_id)

    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")

    role = get_role(db, data.role)
    user.role_id = role.id
    db.commit()
    db.refresh(user)

    logger.info("Admin %s changed role of %s to %s", admin.email, user.email, role.name)
    return user