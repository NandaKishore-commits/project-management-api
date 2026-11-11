from datetime import date, timedelta
from typing import Any

from fastapi import FastAPI

TAGS_METADATA = [
    {"name": "Auth", "description": "Register, log in, and read your own account. Login returns the JWT token that every other endpoint needs."},
    {"name": "Users", "description": "User management. Admins manage users and roles. Project managers can list users to add them to projects."},
    {"name": "Projects", "description": "Projects, their members, and progress statistics. Admins see every project. Everyone else sees only the projects they belong to."},
    {"name": "Tasks", "description": "Tasks with filters, search, sorting and pagination. A team member can change the status only of tasks assigned to them."},
    {"name": "Comments & Activity", "description": "Task comments and the activity history: who did what, and when."},
    {"name": "Dashboard", "description": "Totals, completion percentage, overdue tasks and the most recent activity."},
    {"name": "Health", "description": "Check that the API is running."},
]

API_DESCRIPTION = """
REST API for managing projects, tasks and teams.

## Quick start
1. Click **Authorize**. Enter your email as the *username*, and your password.
2. Open any endpoint, click **Try it out**, then **Execute**.

## Roles
- **admin**: manages users, roles, every project and task.
- **project_manager**: creates projects and manages the projects they belong to.
- **team_member**: sees the projects they belong to and updates the status of tasks assigned to them.

## Pagination
List endpoints accept `page` and `size`, and return `items`, `total`, `page`, `size` and `pages`.

## Errors
Every error has a `detail` message.
    A validation error (422) also lists each wrong field in `errors`.
    An unexpected server error returns 500 with a `request_id`.     
    Every response has an `X-Request-ID` header that matches the line in the server log.
"""


def _in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def body_examples() -> dict[str, dict[str, Any]]:
    """One example request body per input schema. Dates are relative, so they never go stale.

    The ids (project_id, user_id) are placeholders: use ids that exist in your database.
    """
    return {
        "UserCreate": {"full_name": "Ravi Kumar", "email": "ravi@example.com", "password": "Password123"},
        "UserAdminCreate": {"full_name": "Priya Sharma", "email": "priya@example.com", "password": "Password123", "role": "project_manager"},
        "UserUpdate": {"full_name": "Ravi K"},
        "UserStatusUpdate": {"is_active": True},
        "UserRoleUpdate": {"role": "team_member"},
        "ProjectCreate": {"name": "Website Redesign", "description": "Redesign the company website", "start_date": _in_days(0), "end_date": _in_days(90)},
        "ProjectUpdate": {"name": "Website Redesign v2"},
        "MemberAdd": {"user_id": 2},
        "TaskCreate": {"title": "Design homepage", "description": "Create the new homepage layout", "priority": "HIGH", "deadline": _in_days(14), "project_id": 1, "assigned_to": 2},
        "TaskUpdate": {"title": "Design the new homepage"},
        "TaskStatusUpdate": {"status": "IN_PROGRESS"},
        "TaskPriorityUpdate": {"priority": "CRITICAL"},
        "TaskAssign": {"assigned_to": 2},
        "CommentCreate": {"content": "Please use the new brand colors."},
    }


def add_examples(schema: dict[str, Any]) -> None:
    """Puts an example body on every endpoint that takes a JSON body."""
    examples = body_examples()
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            media = operation.get("requestBody", {}).get("content", {}).get("application/json")
            if not media:
                continue
            schema_name = media.get("schema", {}).get("$ref", "").rsplit("/", 1)[-1]
            if schema_name in examples:
                media["example"] = examples[schema_name]


def install_openapi(app: FastAPI) -> None:
    """Makes the app add the example bodies when it builds its OpenAPI file."""
    original_openapi = app.openapi

    def openapi_with_examples() -> dict[str, Any]:
        if app.openapi_schema:  # already built (and patched), reuse it
            return app.openapi_schema
        schema = original_openapi()  # builds the schema and stores it in app.openapi_schema
        add_examples(schema)
        return schema

    app.openapi = openapi_with_examples  # type: ignore[method-assign]