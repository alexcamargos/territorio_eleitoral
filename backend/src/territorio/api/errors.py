"""Standardized RFC 9457-style error responses and domain exception handlers."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse


class ApiError(Exception):
    """Structured API domain exception mapped to HTTP status and error code.

    Attributes:
        status_code: HTTP status code (400, 404, 422, 503).
        code: Machine-readable error code (`INDICATOR_NOT_FOUND`, etc.).
        message: Human-readable Portuguese message.
        details: Optional dictionary with contextual parameters.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initializes an `ApiError`.

        Args:
            status_code: HTTP status code.
            code: Machine-readable error code.
            message: Human-readable Portuguese message.
            details: Optional dictionary with contextual parameters.
        """
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def register_exception_handlers(app: FastAPI) -> None:
    """Registers global `ApiError` and `RequestValidationError` handlers on `app`.

    Args:
        app: FastAPI application instance.
    """

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Parâmetros de requisição inválidos.",
                    "details": {"errors": exc.errors()},
                }
            },
        )
