"""Shared test setup (fixtures).

The environment variables below are set BEFORE the app is imported, so the tests
can never connect to your real PostgreSQL database. Every test gets its own empty
in-memory SQLite database, which disappears when the test ends.
Keep these three lines above the imports.
"""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-" + "0123456789abcdef" * 4
os.environ["LOG_LEVEL"] = "CRITICAL"  # keeps logs/app.log free of test noise

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Role, User
from app.utils.enums import RoleName
from tests.helpers import API, project_payload, task_payload

DEFAULT_PASSWORD = "Password123"

# StaticPool = every connection is the same one. That is what keeps an
# in-memory SQLite database alive between the requests of one test.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def fast_bcrypt():
    """bcrypt is slow on purpose. In tests we lower its cost factor to 4."""
    real_gensalt = bcrypt.gensalt
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            bcrypt, "gensalt",
            lambda rounds=12, prefix=b"2b": real_gensalt(rounds=4, prefix=prefix),
        )
        yield


@pytest.fixture()
def setup_db():
    """Creates all tables + the 3 roles before a test, and removes everything after it."""
    Base.metadata.create_all(test_engine)
    with TestingSession() as session:
        for role in RoleName:
            session.add(Role(name=role.value, description=role.value))
        session.commit()
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture()
def client(setup_db):
    """A test client whose app uses the test database instead of PostgreSQL."""

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(setup_db):
    """A direct database session, for the rare test that must change data the API refuses."""
    with TestingSession() as session:
        yield session


@pytest.fixture()
def make_user(setup_db):
    """Returns a function that creates a user and gives back id, email, password and auth headers."""

    def _make(email: str, role: RoleName = RoleName.TEAM_MEMBER, is_active: bool = True) -> dict:
        with TestingSession() as session:
            role_row = session.scalar(select(Role).where(Role.name == role.value))
            assert role_row is not None, f"Role '{role.value}' is missing from the test database"
            user = User(
                full_name=email.split("@")[0].title(),
                email=email,
                hashed_password=hash_password(DEFAULT_PASSWORD),
                role_id=role_row.id,
                is_active=is_active,
            )
            session.add(user)
            session.commit()
            user_id = user.id
        token = create_access_token(user_id)
        return {
            "id": user_id,
            "email": email,
            "password": DEFAULT_PASSWORD,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _make


# ---------- ready-made people ----------

@pytest.fixture()
def admin(make_user):
    return make_user("admin@test.com", RoleName.ADMIN)


@pytest.fixture()
def manager(make_user):
    return make_user("manager@test.com", RoleName.PROJECT_MANAGER)


@pytest.fixture()
def member(make_user):
    return make_user("member@test.com", RoleName.TEAM_MEMBER)


@pytest.fixture()
def outsider(make_user):
    """A team member who belongs to no project."""
    return make_user("outsider@test.com", RoleName.TEAM_MEMBER)


# ---------- ready-made data ----------

@pytest.fixture()
def project(client, manager, member):
    """A project created by `manager`, with `member` added to it."""
    r = client.post(f"{API}/projects", json=project_payload(), headers=manager["headers"])
    assert r.status_code == 201, r.text
    created = r.json()
    r = client.post(
        f"{API}/projects/{created['id']}/members",
        json={"user_id": member["id"]},
        headers=manager["headers"],
    )
    assert r.status_code == 201, r.text
    return created


@pytest.fixture()
def task(client, manager, member, project):
    """A task in `project`, created by `manager` and assigned to `member`."""
    r = client.post(
        f"{API}/tasks",
        json=task_payload(project["id"], assigned_to=member["id"]),
        headers=manager["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()