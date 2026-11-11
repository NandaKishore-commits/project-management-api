from pydantic import BaseModel


class ErrorOut(BaseModel):
    """Shape of 400, 401, 403, 404 and 409 errors."""
    detail: str


class FieldError(BaseModel):
    field: str
    message: str


class ValidationErrorOut(BaseModel):
    """Shape of the 422 error from Step 17."""
    detail: str = "Validation failed"
    errors: list[FieldError]