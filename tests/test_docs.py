import pytest

from app.core.openapi import body_examples
from app.schemas.comment import CommentCreate
from app.schemas.project import MemberAdd, ProjectCreate, ProjectUpdate
from app.schemas.task import (
    TaskAssign,
    TaskCreate,
    TaskPriorityUpdate,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.schemas.user import (
    UserAdminCreate,
    UserCreate,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)

MODELS = {
    "UserCreate": UserCreate,
    "UserAdminCreate": UserAdminCreate,
    "UserUpdate": UserUpdate,
    "UserStatusUpdate": UserStatusUpdate,
    "UserRoleUpdate": UserRoleUpdate,
    "ProjectCreate": ProjectCreate,
    "ProjectUpdate": ProjectUpdate,
    "MemberAdd": MemberAdd,
    "TaskCreate": TaskCreate,
    "TaskUpdate": TaskUpdate,
    "TaskStatusUpdate": TaskStatusUpdate,
    "TaskPriorityUpdate": TaskPriorityUpdate,
    "TaskAssign": TaskAssign,
    "CommentCreate": CommentCreate,
}


def operations(spec):
    """Yields (method, path, operation) for every endpoint in the OpenAPI file."""
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict):
                yield method.upper(), path, operation


@pytest.fixture()
def spec(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


# ---------- examples ----------

def test_examples_exist_for_every_model():
    assert set(body_examples()) == set(MODELS)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_example_is_valid(name):
    # If you change a schema and forget its example, this test tells you
    MODELS[name].model_validate(body_examples()[name])


def test_json_bodies_have_examples(spec):
    checked = 0
    for method, path, op in operations(spec):
        media = op.get("requestBody", {}).get("content", {}).get("application/json")
        if media:
            assert "example" in media, f"{method} {path} has no example body"
            checked += 1
    assert checked > 0


def test_example_shows_up_on_the_task_endpoint(spec):
    media = spec["paths"]["/api/v1/tasks"]["post"]["requestBody"]["content"]["application/json"]
    assert media["example"]["title"] == "Design homepage"


# ---------- tags and responses ----------

def test_every_tag_is_described(spec):
    described = {t["name"]: t.get("description", "") for t in spec["tags"]}
    used = {tag for _, _, op in operations(spec) for tag in op.get("tags", [])}
    assert used <= set(described), f"tags without a description: {used - set(described)}"
    assert all(described[name] for name in used)


def test_protected_endpoints_document_401(spec):
    protected = [(m, p, op) for m, p, op in operations(spec) if "security" in op]
    assert protected
    for method, path, op in protected:
        assert "401" in op["responses"], f"{method} {path} does not document 401"


def test_endpoints_with_input_document_the_clean_422(spec):
    for method, path, op in operations(spec):
        if op.get("parameters") or op.get("requestBody"):
            assert "422" in op["responses"], f"{method} {path} has no 422"
            schema = op["responses"]["422"]["content"]["application/json"]["schema"]
            assert schema["$ref"].endswith("/ValidationErrorOut"), f"{method} {path}"


def test_docs_pages_load(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200