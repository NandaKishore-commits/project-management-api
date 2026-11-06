from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.schemas.common import reject_null
from app.utils.enums import RoleName

# Spaces around a name are removed automatically ("  Ravi " -> "Ravi")
FullName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)
]


def validate_password_strength(value: str) -> str:
    # bcrypt only handles 72 bytes. Accented or non-English letters use more than 1 byte.
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password is too long")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one letter and one number")
    return value


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None


class UserCreate(BaseModel):
    full_name: FullName
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UserAdminCreate(UserCreate):
    """Used only by admins: same as UserCreate, plus a role."""
    role: RoleName = RoleName.TEAM_MEMBER


class UserUpdate(BaseModel):
    full_name: FullName | None = None
    email: EmailStr | None = None

    @field_validator("full_name", "email")
    @classmethod
    def no_nulls(cls, v):
        return reject_null(v)


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: RoleName  # only admin / project_manager / team_member are accepted


class UserBrief(BaseModel):
    """Small user info, used inside other responses (comments, members, activity)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    is_active: bool
    role: RoleOut
    created_at: datetime