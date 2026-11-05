import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Role, User
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserOut
from app.utils.enums import RoleName

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates a new account. Every new user starts as a **team_member**. "
    "Only an admin can change the role later.",
)
def register(data: UserCreate, db: Session = Depends(get_db)):
    email = data.email.lower()

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    # Nobody can register as admin: the role is always team_member
    role = db.scalar(select(Role).where(Role.name == RoleName.TEAM_MEMBER.value))
    if role is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Roles are not set up. Run: python -m scripts.seed",
        )

    user = User(
        full_name=data.full_name,
        email=email,
        hashed_password=hash_password(data.password),
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Login and get a JWT token",
    description="Send your **email** in the `username` field and your password. "
    "Returns an access token to use as `Authorization: Bearer <token>`.",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == form_data.username.lower()))

    # Same message for "no such email" and "wrong password", so nobody can
    # find out which emails exist.
    if user is None or not verify_password(form_data.password, user.hashed_password):
        logger.warning("Failed login attempt for email: %s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Checked only AFTER the password is correct
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is deactivated")

    logger.info("User logged in: %s", user.email)
    return Token(access_token=create_access_token(user.id))


@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the logged-in user",
)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user