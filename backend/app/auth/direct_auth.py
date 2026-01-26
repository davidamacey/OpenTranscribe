"""
Direct database authentication module for troubleshooting purposes.
This bypasses the SQLAlchemy ORM relationships to ensure login works.
"""

import os
from datetime import datetime
from datetime import timedelta

import psycopg2
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing with bcrypt_sha256 to handle long passwords properly
# bcrypt_sha256 pre-hashes with SHA256 to work around bcrypt's 72-byte limitation
# We keep "bcrypt" in the list to verify existing hashes, but new hashes use bcrypt_sha256
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],  # bcrypt_sha256 for new, bcrypt for legacy
    deprecated=["bcrypt"],  # Mark plain bcrypt as deprecated (will auto-upgrade on verify)
    bcrypt_sha256__default_rounds=12,
    bcrypt__default_rounds=12,
)

# Database connection parameters
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "transcribe_app")


def get_db_connection():
    """Get a direct database connection."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    return conn


def verify_password(plain_password, hashed_password):
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def direct_authenticate_user(email: str, password: str):
    """
    Directly authenticate a user by email and password using a raw database connection.

    This function provides a direct database authentication mechanism that bypasses
    the SQLAlchemy ORM, which can sometimes have relationship loading issues.

    Args:
        email: The user's email address
        password: The user's plaintext password

    Returns:
        dict: User data if authentication is successful
        None: If authentication fails
    """
    import logging

    logger = logging.getLogger(__name__)

    # Basic input validation
    if not email or not password:
        logger.warning("Authentication attempt with empty email or password")
        return None

    # Normalize email to lowercase and trim whitespace
    email = email.lower().strip()

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query the user
        cursor.execute(
            'SELECT id, email, hashed_password, full_name, role, is_active, is_superuser, auth_type FROM "user" WHERE email = %s',
            (email,),
        )

        user = cursor.fetchone()

        if not user:
            logger.info(f"Authentication failed: no user found with email {email}")
            return None

        (
            user_id,
            user_email,
            hashed_password,
            full_name,
            role,
            is_active,
            is_superuser,
            auth_type,
        ) = user

        # LDAP users cannot authenticate via password
        if auth_type == "ldap":
            logger.info(
                f"Authentication failed: user {email} is LDAP type, cannot use password auth"
            )
            return None

        # Verify password
        if not verify_password(password, hashed_password):
            logger.warning(f"Authentication failed: incorrect password for user {email}")
            return None

        # Check if user is active
        if not is_active:
            logger.warning(f"Authentication failed: user {email} is inactive")
            return None

        logger.info(f"Authentication successful for user {email}")
        return {
            "id": user_id,
            "email": user_email,
            "full_name": full_name,
            "role": role,
            "is_active": is_active,
            "is_superuser": is_superuser,
        }

    except Exception as e:
        logger.error(f"Database authentication error: {str(e)}")
        return None
    finally:
        # Ensure connections are always closed
        if conn:
            try:
                cursor.close()
                conn.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")
