from fastapi import FastAPI

from app import models  # noqa: F401  (makes sure all 7 models are loaded)
from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="REST API for managing projects, tasks and teams.",
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"], summary="Check that the API is running")
def health():
    return {"status": "ok"}