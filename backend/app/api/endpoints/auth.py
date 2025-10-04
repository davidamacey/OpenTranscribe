import logging
import os
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from jose import jwt
from sqlalchemy.orm import Session

from app.auth.direct_auth import create_access_token as direct_create_token
from app.auth.direct_auth import direct_authenticate_user
from app.core.config import settings
from app.core.security import authenticate_user
from app.core.security import get_password_hash
from app.db.base import get_db
from app.models.user import User
from app.schemas.user import Token
from app.schemas.user import TokenPayload
from app.schemas.user import User as UserOut
from app.schemas.user import User as UserSchema
from app.schemas.user import UserCreate

router = APIRouter()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Get the current user from the JWT token.

    Token payload uses UUID (sub field contains user UUID string).
    Internal database queries use integer ID for performance.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_uuid_str: str = payload.get("sub")  # UUID string from token
        user_role: str = payload.get("role")  # Extract role from token
        if user_uuid_str is None:
            raise credentials_exception

        # Validate UUID format
        try:
            user_uuid = UUID(user_uuid_str)
        except ValueError:
            raise credentials_exception

        token_data = TokenPayload(sub=user_uuid_str)
    except JWTError as e:
        raise credentials_exception from e

    try:
        # Look up user by UUID (indexed for performance)
        user = db.query(User).filter(User.uuid == user_uuid).first()
        if user is None:
            raise credentials_exception
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")

        # If role in token differs from DB, prioritize token's role
        # This ensures newly granted admin rights take effect immediately
        if user_role and user.role != user_role:
            logger.info(
                f"Updating user {user.id} role from {user.role} to {user_role} based on token"
            )
            user.role = user_role
            db.commit()

        return user
    except Exception as e:
        # Handle database connection errors or other issues
        logger.error(f"Error retrieving user: {e}")
        # In testing environment, we can create a mock user with the UUID from the token
        testing_environment = os.environ.get("TESTING", "False").lower() == "true"
        if testing_environment:
            logger.info(f"Creating mock user for testing with uuid {token_data.sub}")
            # For tests, create a basic user object with the UUID from the token
            user = User(
                uuid=UUID(token_data.sub),
                email="test@example.com",
                is_active=True,
                is_superuser=False,
            )
            return user
        # Re-raise the exception in production
        raise


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Check if the current user is active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Check if the current user is an admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Check if the current user is a superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - superuser required",
        )
    return current_user


def _authenticate_testing_user(db: Session, username: str, password: str) -> str:
    """Authenticate user in testing environment.

    Args:
        db: Database session
        username: Username to authenticate
        password: Password to verify

    Returns:
        User UUID string

    Raises:
        HTTPException: If authentication fails
    """
    logger.info(f"Testing environment detected, using ORM auth for: {username}")
    user = authenticate_user(db, username, password)

    if not user:
        logger.warning(f"Failed login attempt for user: {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {username}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )

    return str(user.uuid)  # Return UUID string for token


def _authenticate_production_user(db: Session, username: str, password: str) -> tuple[str, dict]:
    """Authenticate user in production environment.

    Args:
        db: Database session
        username: Username to authenticate
        password: Password to verify

    Returns:
        Tuple of (user_uuid_string, user_data_dict)

    Raises:
        HTTPException: If authentication fails
    """
    # Try direct auth first, then fall back to ORM
    user_data = direct_authenticate_user(username, password)

    if user_data:
        logger.info(f"Direct authentication successful for user: {username}")
        # Get UUID from user_data or fallback to database lookup
        if "uuid" in user_data:
            user_uuid_str = user_data["uuid"]
        else:
            # Direct auth returned integer ID, look up UUID
            user = db.query(User).filter(User.id == user_data["id"]).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )
            user_uuid_str = str(user.uuid)
            user_data["uuid"] = user_uuid_str

        is_active = user_data.get("is_active", True)

        if not is_active:
            logger.warning(f"Login attempt for inactive user: {username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user account",
            )

        return user_uuid_str, user_data
    else:
        # Fall back to ORM-based auth
        logger.info(f"Direct auth failed, trying ORM auth for: {username}")
        user = authenticate_user(db, username, password)

        if not user:
            logger.warning(f"Failed login attempt for user: {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user account",
            )

        return str(user.uuid), {}


def _get_user_role(db: Session, user_uuid_str: str, user_data: dict = None) -> str:
    """Get user role for token generation.

    Args:
        db: Database session
        user_uuid_str: User UUID string
        user_data: Optional user data from direct auth

    Returns:
        User role string
    """
    if user_data and "role" in user_data:
        return user_data["role"]

    # Get role from database if not available in direct auth
    user_uuid = UUID(user_uuid_str)
    user_db = db.query(User).filter(User.uuid == user_uuid).first()
    return user_db.role if user_db else None


@router.post("/token", response_model=Token)
@router.post("/login", response_model=Token)  # Add alias for frontend compatibility
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """OAuth2 compatible token login, get an access token for future requests.

    Args:
        form_data: OAuth2 form data with username and password
        db: Database session

    Returns:
        Access token and token type

    Raises:
        HTTPException: If authentication fails
    """
    logger.info(f"Login attempt for user: {form_data.username}")

    try:
        testing_environment = os.environ.get("TESTING", "False").lower() == "true"

        if testing_environment:
            user_uuid_str = _authenticate_testing_user(db, form_data.username, form_data.password)
            user_data = {}
        else:
            user_uuid_str, user_data = _authenticate_production_user(
                db, form_data.username, form_data.password
            )

        # Get user's role for inclusion in the token
        user_role = _get_user_role(db, user_uuid_str, user_data)

        # Generate the JWT token with role information
        # Token payload contains UUID string in 'sub' field (production-grade security)
        access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        token_data = {"sub": user_uuid_str}  # UUID string in token
        if user_role:
            token_data["role"] = user_role

        access_token = direct_create_token(data=token_data, expires_delta=access_token_expires)

        logger.info(f"Login successful for user: {form_data.username}")
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during authentication",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post("/register", response_model=UserSchema)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user
    """
    # Check if email already exists
    user_exists = db.query(User).filter(User.email == user_in.email).first()

    if user_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    db_user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        role="user",  # Default role
        is_active=True,
        is_superuser=False,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


@router.get("/me", response_model=UserOut, summary="Get current user")
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Get current user using the current_user dependency
    """
    return current_user
