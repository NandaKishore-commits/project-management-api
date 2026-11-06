from fastapi import APIRouter

from app.api.v1.endpoints import auth

api_router = APIRouter()

api_router.include_router(auth.router)
# Next steps will add: users, projects, tasks, comments