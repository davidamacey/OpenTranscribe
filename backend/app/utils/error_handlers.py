import logging
from functools import wraps
from typing import Callable

from fastapi import HTTPException
from fastapi import status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def handle_database_errors(func: Callable) -> Callable:
    """
    Decorator to handle common database errors.

    Args:
        func: Function to wrap

    Returns:
        Wrapped function with error handling
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            # Rollback session if available in kwargs
            if 'db' in kwargs and isinstance(kwargs['db'], Session):
                kwargs['db'].rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation failed"
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred"
            )

    return wrapper


def handle_not_found(resource_name: str = "Resource") -> Callable:
    """
    Decorator factory to handle resource not found errors.

    Args:
        resource_name: Name of the resource for error message

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if result is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{resource_name} not found"
                )
            return result
        return wrapper
    return decorator


class ErrorHandler:
    """Centralized error handling utility class."""

    @staticmethod
    def database_error(operation: str, error: Exception) -> HTTPException:
        """
        Create standardized database error response.

        Args:
            operation: Description of the operation that failed
            error: The original error

        Returns:
            HTTPException with appropriate status and message
        """
        logger.error(f"Database error during {operation}: {error}")
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during {operation}"
        )

    @staticmethod
    def validation_error(message: str) -> HTTPException:
        """
        Create standardized validation error response.

        Args:
            message: Validation error message

        Returns:
            HTTPException with 400 status
        """
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    @staticmethod
    def not_found_error(resource: str) -> HTTPException:
        """
        Create standardized not found error response.

        Args:
            resource: Name of the resource that wasn't found

        Returns:
            HTTPException with 404 status
        """
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found"
        )

    @staticmethod
    def unauthorized_error(message: str = "Access denied") -> HTTPException:
        """
        Create standardized unauthorized error response.

        Args:
            message: Authorization error message

        Returns:
            HTTPException with 403 status
        """
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )

    @staticmethod
    def file_processing_error(operation: str, error: Exception) -> HTTPException:
        """
        Create standardized file processing error response.

        Args:
            operation: Description of the file operation that failed
            error: The original error

        Returns:
            HTTPException with appropriate status and message
        """
        logger.error(f"File processing error during {operation}: {error}")
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File processing failed during {operation}"
        )
