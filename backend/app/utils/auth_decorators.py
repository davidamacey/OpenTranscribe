import logging
from typing import Callable
from functools import wraps
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.media import MediaFile

logger = logging.getLogger(__name__)


def require_file_ownership(func: Callable) -> Callable:
    """
    Decorator to ensure user owns the specified file.
    
    The decorated function must have 'db', 'current_user', and 'file_id' parameters.
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function with ownership check
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract parameters from kwargs
        db = kwargs.get('db')
        current_user = kwargs.get('current_user') 
        file_id = kwargs.get('file_id')
        
        if not all([db, current_user, file_id]):
            raise ValueError("Function must have 'db', 'current_user', and 'file_id' parameters")
        
        # Check if user owns the file
        file_exists = db.query(MediaFile).filter(
            MediaFile.id == file_id,
            MediaFile.user_id == current_user.id
        ).first()
        
        if not file_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        return func(*args, **kwargs)
    
    return wrapper


def require_admin_or_ownership(resource_model, id_param: str = 'resource_id', 
                              user_id_field: str = 'user_id'):
    """
    Decorator factory to ensure user is admin or owns the specified resource.
    
    Args:
        resource_model: SQLAlchemy model class
        id_param: Parameter name containing the resource ID
        user_id_field: Field name in the model that contains the user ID
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            db = kwargs.get('db')
            current_user = kwargs.get('current_user')
            resource_id = kwargs.get(id_param)
            
            if not all([db, current_user, resource_id]):
                raise ValueError(f"Function must have 'db', 'current_user', and '{id_param}' parameters")
            
            # Check if user is admin
            if current_user.is_admin:
                return func(*args, **kwargs)
            
            # Check if user owns the resource
            resource = db.query(resource_model).filter(
                getattr(resource_model, 'id') == resource_id
            ).first()
            
            if not resource or getattr(resource, user_id_field) != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Resource not found or access denied"
                )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """
    Decorator to ensure user has admin privileges.
    
    The decorated function must have 'current_user' parameter.
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function with admin check
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        
        if not current_user:
            raise ValueError("Function must have 'current_user' parameter")
        
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required"
            )
        
        return func(*args, **kwargs)
    
    return wrapper


def require_verified_user(func: Callable) -> Callable:
    """
    Decorator to ensure user account is verified.
    
    The decorated function must have 'current_user' parameter.
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function with verification check
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        
        if not current_user:
            raise ValueError("Function must have 'current_user' parameter")
        
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account verification required"
            )
        
        return func(*args, **kwargs)
    
    return wrapper


class AuthorizationHelper:
    """Helper class for common authorization operations."""
    
    @staticmethod
    def check_file_access(db: Session, file_id: int, user: User) -> MediaFile:
        """
        Check if user has access to a file and return it.
        
        Args:
            db: Database session
            file_id: File ID
            user: Current user
            
        Returns:
            MediaFile object if user has access
            
        Raises:
            HTTPException: If file not found or access denied
        """
        file_obj = db.query(MediaFile).filter(
            MediaFile.id == file_id,
            MediaFile.user_id == user.id
        ).first()
        
        if not file_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        return file_obj
    
    @staticmethod
    def check_admin_or_owner(resource, user: User, owner_field: str = 'user_id') -> bool:
        """
        Check if user is admin or owns the resource.
        
        Args:
            resource: Resource object
            user: Current user
            owner_field: Field name containing the owner user ID
            
        Returns:
            True if user has access, False otherwise
        """
        if user.is_admin:
            return True
        
        return getattr(resource, owner_field, None) == user.id
    
    @staticmethod
    def require_resource_access(db: Session, model_class, resource_id: int, 
                               user: User, owner_field: str = 'user_id'):
        """
        Generic function to check resource access.
        
        Args:
            db: Database session
            model_class: SQLAlchemy model class
            resource_id: Resource ID
            user: Current user
            owner_field: Field name containing the owner user ID
            
        Returns:
            Resource object if user has access
            
        Raises:
            HTTPException: If resource not found or access denied
        """
        resource = db.query(model_class).filter(
            model_class.id == resource_id
        ).first()
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found"
            )
        
        if not AuthorizationHelper.check_admin_or_owner(resource, user, owner_field):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return resource