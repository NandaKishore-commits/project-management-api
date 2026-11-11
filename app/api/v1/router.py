from fastapi import APIRouter

from app.api.v1.endpoints import auth, comments, dashboard, projects, tasks, users
from app.core.responses import error_responses

api_router = APIRouter()

api_router.include_router(auth.router, responses=error_responses(401, 403, 409, 422))
api_router.include_router(users.router, responses=error_responses(400, 401, 403, 404, 409, 422))
api_router.include_router(projects.router, responses=error_responses(400, 401, 403, 404, 409, 422))
api_router.include_router(tasks.router, responses=error_responses(400, 401, 403, 404, 422))
api_router.include_router(comments.router, responses=error_responses(401, 403, 404, 422))
api_router.include_router(dashboard.router, responses=error_responses(401))