from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Role, User
from app.utils.enums import RoleName

ROLES = {
    RoleName.ADMIN.value: "Full access to everything",
    RoleName.PROJECT_MANAGER.value: "Manages projects and tasks",
    RoleName.TEAM_MEMBER.value: "Works on assigned tasks",
}

ADMIN_NAME = "Super Admin"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin@12345"  # development only: change it for real use


def seed_roles(db: Session) -> None:
    for name, description in ROLES.items():
        exists = db.scalar(select(Role).where(Role.name == name))
        if not exists:
            db.add(Role(name=name, description=description))
            print(f"Created role: {name}")
    db.commit()


def seed_admin(db: Session) -> None:
    admin_role = db.scalar(select(Role).where(Role.name == RoleName.ADMIN.value))
    if admin_role is None:
        raise RuntimeError("Admin role is missing. Run seed_roles first.")

    exists = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if exists:
        print("Admin user already exists. Skipped.")
        return

    db.add(
        User(
            full_name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            role_id=admin_role.id,
        )
    )
    db.commit()
    print(f"Created admin user: {ADMIN_EMAIL}")


def run() -> None:
    db = SessionLocal()
    try:
        seed_roles(db)
        seed_admin(db)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run()