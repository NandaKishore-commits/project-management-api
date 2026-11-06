import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

logger = logging.getLogger(__name__)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def register_exception_handlers(app: FastAPI) -> None:
    # Every error body has a "detail" string, so a frontend can always show it.
    # (HTTPException, used for 401/403/404/409 in the endpoints, already
    # returns {"detail": "..."}, so it needs no handler.)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = err.get("loc", ())
            # ("body", "title") -> "title"; a whole-body error -> "body"
            field = ".".join(str(part) for part in loc[1:]) or (str(loc[0]) if loc else "body")
            message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
            errors.append({"field": field, "message": message})
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed", "errors": errors},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        # A safety net: the endpoints check for duplicates first, but two requests
        # at the same moment can still hit the database's UNIQUE rule.
        logger.warning(
            "[%s] Database integrity error on %s %s: %s",
            get_request_id(request), request.method, request.url.path, exc.orig,
        )
        return JSONResponse(
            status_code=409,
            content={"detail": "This conflicts with existing data (for example a duplicate)"},
        )

    @app.exception_handler(OperationalError)
    async def database_unavailable_handler(request: Request, exc: OperationalError):
        logger.error(
            "[%s] Database unavailable on %s %s: %s",
            get_request_id(request), request.method, request.url.path, exc.orig,
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "The database is temporarily unavailable. Please try again later."},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        request_id = get_request_id(request)
        # The full traceback goes to the log file only, never to the client
        logger.error(
            "[%s] Unhandled error on %s %s",
            request_id, request.method, request.url.path, exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )