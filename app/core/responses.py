import copy
from typing import Any

from app.schemas.errors import ErrorOut, ValidationErrorOut


def _error(model, description: str, example: dict) -> dict[str, Any]:
    return {
        "model": model,
        "description": description,
        "content": {"application/json": {"example": example}},
    }


_DEFINITIONS: dict[int, dict[str, Any]] = {
    400: _error(
        ErrorOut,
        "A business rule was broken. The `detail` field says which one.",
        {"detail": "Deadline cannot be after the project end date (2027-01-31)"},
    ),
    401: _error(
        ErrorOut,
        "Not logged in, or the token is invalid or expired, or the user is deactivated.",
        {"detail": "Not authenticated"},
    ),
    403: _error(
        ErrorOut,
        "Logged in, but not allowed to do this.",
        {"detail": "You do not have permission to do this"},
    ),
    404: _error(
        ErrorOut,
        "The record does not exist, or it was deleted.",
        {"detail": "Project not found"},
    ),
    409: _error(
        ErrorOut,
        "Conflict with existing data, for example a duplicate email.",
        {"detail": "Email already registered"},
    ),
    422: _error(
        ValidationErrorOut,
        "The data has the wrong shape. Each wrong field is listed in `errors`.",
        {
            "detail": "Validation failed",
            "errors": [{"field": "deadline", "message": "Deadline cannot be in the past"}],
        },
    ),
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Builds the `responses=` argument for the given status codes."""
    return {code: copy.deepcopy(_DEFINITIONS[code]) for code in codes}