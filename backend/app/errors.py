"""
Standardized Error Handling Module
Provides consistent error responses across the API
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any, Dict
from enum import Enum
import traceback
import logging

# Configure logging
logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Standard error codes for categorizing errors"""
    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    RATE_LIMITED = "RATE_LIMITED"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    GIT_ERROR = "GIT_ERROR"


class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = False
    error: str
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class AppException(HTTPException):
    """
    Custom application exception with structured error data
    """
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(status_code=status_code, detail=message)


# Convenience exception classes
class NotFoundError(AppException):
    """Resource not found (404)"""
    def __init__(self, resource: str, identifier: str = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with ID '{identifier}' not found"
        super().__init__(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            message=message,
            details={"resource": resource, "identifier": identifier}
        )


class ValidationError(AppException):
    """Validation error (400)"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details=details
        )


class ConflictError(AppException):
    """Conflict error (409)"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            status_code=409,
            code=ErrorCode.CONFLICT,
            message=message,
            details=details
        )


class AlreadyExistsError(AppException):
    """Resource already exists (409). Distinct from ConflictError so the
    response carries `code=ALREADY_EXISTS` — used by the relations API
    (CB-1971) and any other create endpoint that wants to differentiate
    duplicate-rejected from generic conflict."""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            status_code=409,
            code=ErrorCode.ALREADY_EXISTS,
            message=message,
            details=details
        )


class CycleDetectedError(AppException):
    """Cycle in a transitive relation graph (409). CB-1977 — distinguishes
    cycle rejection from generic validation/conflict so callers can render
    `details.path` (the closed cycle in canonical family-graph direction)
    without string-matching the message."""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            status_code=409,
            code=ErrorCode.CYCLE_DETECTED,
            message=message,
            details=details
        )


class DatabaseError(AppException):
    """Database operation error (500)"""
    def __init__(self, message: str = "Database operation failed", details: Dict[str, Any] = None):
        super().__init__(
            status_code=500,
            code=ErrorCode.DATABASE_ERROR,
            message=message,
            details=details
        )


class ExternalServiceError(AppException):
    """External service error (502)"""
    def __init__(self, service: str, message: str = None, details: Dict[str, Any] = None):
        msg = f"External service '{service}' error"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(
            status_code=502,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=msg,
            details={"service": service, **(details or {})}
        )


class AIServiceError(AppException):
    """AI service error (502)"""
    def __init__(self, message: str = "AI service unavailable", details: Dict[str, Any] = None):
        super().__init__(
            status_code=502,
            code=ErrorCode.AI_SERVICE_ERROR,
            message=message,
            details=details
        )


class GitError(AppException):
    """Git operation error (500)"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            status_code=500,
            code=ErrorCode.GIT_ERROR,
            message=message,
            details=details
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handler for AppException - returns structured error response
    """
    error_response = ErrorResponse(
        success=False,
        error=exc.code.value,
        code=exc.code.value,
        message=exc.message,
        details=exc.details
    )

    logger.warning(
        f"AppException: {exc.code.value} - {exc.message}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "details": exc.details
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True)
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handler for standard HTTPException - converts to structured format
    """
    # Determine error code from status
    code = ErrorCode.INTERNAL_ERROR
    if exc.status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif exc.status_code == 400:
        code = ErrorCode.BAD_REQUEST
    elif exc.status_code == 401:
        code = ErrorCode.UNAUTHORIZED
    elif exc.status_code == 403:
        code = ErrorCode.FORBIDDEN
    elif exc.status_code == 409:
        code = ErrorCode.CONFLICT
    elif exc.status_code == 429:
        code = ErrorCode.RATE_LIMITED

    error_response = ErrorResponse(
        success=False,
        error=code.value,
        code=code.value,
        message=str(exc.detail)
    )

    logger.warning(
        f"HTTPException: {exc.status_code} - {exc.detail}",
        extra={"path": request.url.path}
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True)
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler for unhandled exceptions - logs and returns generic error
    """
    # Log the full traceback
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        extra={
            "path": request.url.path,
            "traceback": traceback.format_exc()
        },
        exc_info=True
    )

    error_response = ErrorResponse(
        success=False,
        error=ErrorCode.INTERNAL_ERROR.value,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An unexpected error occurred. Please try again later."
    )

    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(exclude_none=True)
    )


def setup_exception_handlers(app):
    """
    Register all exception handlers with the FastAPI app
    """
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
