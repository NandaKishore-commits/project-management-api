# Project & Team Management API

REST API for managing projects, tasks and teams. Administrators and project managers create projects and tasks, assign them to team members and track progress. Team members see their projects and update the status of the tasks assigned to them.

Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, **Alembic** and **JWT** authentication.

> Submitted for the **Backend Developer** track: API, database, authentication, validation, documentation and tests. The frontend is not part of this submission.

**Demo video:** <PASTE THE VIDEO LINK HERE>

## Features

- JWT login, bcrypt password hashing and role-based access control (admin, project manager, team member)
- User management: create users, update profiles, activate or deactivate, assign roles
- Projects: create, update, soft delete, members, progress statistics
- Tasks: create, update, soft delete, assign, change status and priority, deadline validation, "my tasks"
- Search, filters, sorting and pagination on every list
- Task comments and an activity history (who did what, and when)
- Dashboard statistics
- Input validation with one consistent error format
- Request logging with request ids, and rotating log files
- Alembic migrations, Swagger and ReDoc documentation, automated tests

## Tech stack

| Part | Technology |
|---|---|
| Language | Python 3.13 (3.11 or newer works) |
| Web framework | FastAPI, served by Uvicorn |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy 2, Alembic |
| Validation | Pydantic v2 |
| Authentication | PyJWT (JWT), bcrypt |
| Tests | pytest, httpx (in-memory SQLite) |

## Quick start

**Requirements:** Python 3.11+, PostgreSQL and Git.

**1. Clone and install**

```bash
git clone https://github.com/NandaKishore-commits/project-management-api.git
cd project-management-api
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

**2. Create the database**

Create an empty PostgreSQL database named `pm_db` (in pgAdmin, or `psql -U postgres -c "CREATE DATABASE pm_db;"`).

**3. Configure the environment**

```bash
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Edit `.env` and set your database password and a new secret key. Generate a key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Meaning | Example |
|---|---|---|
| `DATABASE_URL` | Database connection | `postgresql+psycopg2://postgres:PASSWORD@localhost:5432/pm_db` |
| `SECRET_KEY` | Signs the JWT tokens. Keep it secret. | a long random string |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime | `60` |
| `LOG_LEVEL` | Logging detail | `INFO` |

If the password contains `@`, `#`, `/` or `:`, write them as `%40`, `%23`, `%2F`, `%3A`.

**4. Create the tables and the first admin**

```bash
alembic upgrade head
python -m scripts.seed
```

**5. Run**

```bash
uvicorn app.main:app --reload
```

| Address | What it is |
|---|---|
| http://127.0.0.1:8000/docs | Swagger UI (interactive) |
| http://127.0.0.1:8000/redoc | ReDoc (read-only) |
| http://127.0.0.1:8000/health | Health check |

**Default admin (development only):** `admin@example.com` / `Admin@12345`. It is created by `scripts/seed.py`. Change `ADMIN_PASSWORD` in that file before seeding any shared or deployed database. There is no change-password endpoint yet.

**Using the API in Swagger:** click **Authorize**, enter the email as *username* with the password, then try any endpoint.

## Roles and permissions

| Action | Admin | Project manager | Team member |
|---|:-:|:-:|:-:|
| Manage users, roles, activate or deactivate | ✅ | ❌ | ❌ |
| List users | ✅ | ✅ | ❌ |
| Create a project | ✅ | ✅ | ❌ |
| See projects and tasks | all | projects they belong to | projects they belong to |
| Edit or delete a project, manage its members | any | projects they belong to | ❌ |
| Create, edit, delete and assign tasks | any | projects they belong to | ❌ |
| Change a task's priority | any | projects they belong to | ❌ |
| Change a task's status | any | projects they belong to | only tasks assigned to them |
| Comment on a task | any | projects they belong to | projects they belong to |

## API overview

All paths start with `/api/v1`. Every endpoint except register and login needs `Authorization: Bearer <token>`.

| Method | Path | Who |
|---|---|---|
| POST | `/auth/register` | Public (always creates a team member) |
| POST | `/auth/login` | Public |
| GET | `/auth/me` | Any logged-in user |
| GET | `/users` | Admin, project manager |
| POST | `/users` | Admin |
| GET | `/users/{id}` | Admin |
| PUT | `/users/{id}` | Admin, or the user themself |
| PATCH | `/users/{id}/status` | Admin |
| PATCH | `/users/{id}/role` | Admin |
| POST | `/projects` | Admin, project manager |
| GET | `/projects` | Any (own projects, admin sees all) |
| GET | `/projects/{id}` | Members, admin |
| PUT / DELETE | `/projects/{id}` | Admin, project manager of the project |
| GET | `/projects/{id}/members` | Members, admin |
| POST | `/projects/{id}/members` | Admin, project manager of the project |
| DELETE | `/projects/{id}/members/{user_id}` | Admin, project manager of the project |
| GET | `/projects/{id}/stats` | Members, admin |
| POST | `/tasks` | Admin, project manager of the project |
| GET | `/tasks` | Any (own projects, admin sees all) |
| GET | `/tasks/my` | Any (tasks assigned to me) |
| GET | `/tasks/{id}` | Members, admin |
| PUT / DELETE | `/tasks/{id}` | Admin, project manager of the project |
| PATCH | `/tasks/{id}/status` | Admin, project manager of the project, or the assignee |
| PATCH | `/tasks/{id}/priority` | Admin, project manager of the project |
| PATCH | `/tasks/{id}/assign` | Admin, project manager of the project |
| POST / GET | `/tasks/{id}/comments` | Members, admin |
| GET | `/tasks/{id}/activity` | Members, admin |
| GET | `/projects/{id}/activity` | Members, admin |
| GET | `/dashboard/stats` | Any (own projects, admin sees all) |

The full, interactive list with example requests is in Swagger at `/docs`. The OpenAPI file is `docs/openapi.json`.

### Pagination, filtering and sorting

```
GET /api/v1/tasks?status=IN_PROGRESS&priority=HIGH&search=login&sort_by=deadline&order=asc&page=1&size=10
```

Every list returns:

```json
{ "items": [], "total": 57, "page": 1, "size": 10, "pages": 6 }
```

## Business rules

- Registration always creates a **team member**. Only an admin can change a role.
- `end_date` must be after `start_date`.
- A task deadline cannot be in the past, and cannot be after the project's end date.
- A task can only be assigned to an **active member** of its project.
- Removing a member **unassigns** their tasks. The project creator cannot be removed.
- An admin cannot deactivate themselves or change their own role.
- A deactivated user cannot log in, and their existing token stops working at once.
- Projects and tasks use **soft delete**. Deleting a project hides its tasks too.
- Every project, member, task and comment change writes an **activity log** entry in the same database transaction. User role and status changes are written to the application log instead.

## Errors

Every error has a `detail` message.

| Code | Meaning |
|---|---|
| 400 | A business rule was broken |
| 401 | Not logged in, or the token is invalid or expired |
| 403 | Logged in, but not allowed |
| 404 | Not found, or deleted |
| 409 | Conflict, for example a duplicate email |
| 422 | Invalid input. Each wrong field is listed in `errors`. |
| 500 | Unexpected error. The response includes a `request_id`, and the traceback is only in the log. |

```json
{ "detail": "Validation failed", "errors": [{ "field": "deadline", "message": "Deadline cannot be in the past" }] }
```

## Logging

- Every request is logged with a short id, method, path, status and time. The same id is returned in the `X-Request-ID` header.
- Files: `logs/app.log` (everything) and `logs/errors.log` (errors with tracebacks). Both rotate at 1 MB.
- Passwords, tokens and request bodies are never logged.

## Database

PostgreSQL with 7 tables, created by Alembic migrations in `alembic/versions/`.

![ER diagram](docs/er-diagram.png)

The diagram is also in [`docs/er-diagram.md`](docs/er-diagram.md).

## Tests

```bash
pytest
```

The tests use an in-memory SQLite database and never touch PostgreSQL. They cover authentication, role permissions, validation, business rules, filtering, pagination, comments, the dashboard, error handling and the API documentation.

## Project structure

```
project-management-api/
├── app/
│   ├── main.py                  # creates the app
│   ├── api/
│   │   ├── deps.py              # get_current_user, role guards
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/       # auth, users, projects, tasks, comments, dashboard
│   ├── core/                    # config, security, logging, middleware, exceptions, openapi
│   ├── db/                      # Base, engine and session
│   ├── models/                  # SQLAlchemy tables
│   ├── schemas/                 # Pydantic request and response shapes
│   ├── services/                # permissions, activity logging
│   └── utils/                   # enums, pagination
├── alembic/                     # migrations
├── docs/                        # openapi.json, ER diagram, screenshots
├── scripts/                     # seed.py, export_openapi.py
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## Screenshots

![Swagger home](docs/screenshots/01-swagger-home.png)
![Validation error](docs/screenshots/03-validation-422.png)
![Forbidden for a team member](docs/screenshots/04-forbidden-403-member.png)
![Activity history](docs/screenshots/07-activity-history.png)
![Dashboard](docs/screenshots/08-dashboard.png)
![Tests passing](docs/screenshots/12-tests-passing.png)

More screenshots are in `docs/screenshots/`.

## Limitations and possible improvements

- No frontend (Backend Developer track).
- Not implemented: WebSockets, email notifications, file attachments, Docker, deployment.
- No refresh tokens, password change or reset, or rate limiting.
- Tests run on SQLite, while the application runs on PostgreSQL.

## Author

Nanda Kishore Putta · [GitHub](https://github.com/NandaKishore-commits)