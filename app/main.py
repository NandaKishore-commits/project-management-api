import logging

from fastapi import FastAPI

from app import models  # noqa: F401  (makes sure all 7 models are loaded)
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.middleware import register_middleware
from app.core.openapi import API_DESCRIPTION, TAGS_METADATA, install_openapi

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    swagger_ui_parameters={
        "persistAuthorization": True,   # keep the login after a page refresh
        "displayRequestDuration": True,  # show how long each request took
        "tryItOutEnabled": True,         # "Try it out" is open at once
    },
)

register_middleware(app)
register_exception_handlers(app)
install_openapi(app)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"], summary="Check that the API is running")
def health():
    return {"status": "ok"}


logger.info("%s loaded (log level %s)", settings.PROJECT_NAME, settings.LOG_LEVEL)