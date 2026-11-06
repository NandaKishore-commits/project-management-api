import logging
import time
import uuid

from fastapi import FastAPI, Request

logger = logging.getLogger("app.access")


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # A short id that ties together the log line, the response header
        # and (if something crashes) the error message.
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)  # your endpoint runs here

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id

        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO
        # Health checks run every few seconds on hosting platforms: keep them quiet
        if request.url.path == "/health" and level == logging.INFO:
            level = logging.DEBUG

        logger.log(
            level,
            "[%s] %s %s -> %s (%.1f ms) client=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.client.host if request.client else "-",
        )
        return response