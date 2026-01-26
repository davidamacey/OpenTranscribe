import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from typing import Optional
from typing import Union

from fastapi import Cookie
from fastapi import HTTPException
from fastapi import status
from jose import JWTError
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User


def _create_password_context() -> CryptContext:
    """
    Create password hashing context based on FIPS mode configuration.

    FIPS 140-2 compliant hashing uses PBKDF2-SHA256 (NIST SP 800-132).
    Non-FIPS mode supports bcrypt_sha256, bcrypt, and PBKDF2 for backward compatibility.

    Returns:
        CryptContext configured for the appropriate hashing schemes
    """
    if settings.FIPS_MODE:
        # FIPS mode: Use only PBKDF2-SHA256 (NIST SP 800-132 compliant)
        # Auto-upgrade from bcrypt/bcrypt_sha256 on successful verify
        return CryptContext(
            schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"],
            default="pbkdf2_sha256",
            deprecated=["bcrypt_sha256", "bcrypt"],
            pbkdf2_sha256__rounds=settings.PBKDF2_ITERATIONS,
            bcrypt_sha256__default_rounds=12,
            bcrypt__default_rounds=12,
        )
    else:
        # Standard mode: bcrypt_sha256 for new hashes, support legacy bcrypt and PBKDF2
        # Auto-upgrade from plain bcrypt on successful verify
        return CryptContext(
            schemes=["bcrypt_sha256", "bcrypt", "pbkdf2_sha256"],
            default="bcrypt_sha256",
            deprecated=["bcrypt"],
            bcrypt_sha256__default_rounds=12,
            bcrypt__default_rounds=12,
            pbkdf2_sha256__rounds=settings.PBKDF2_ITERATIONS,
        )


# Global password context - recreated when needed
pwd_context = _create_password_context()


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[dict] = None,
) -> str:
    """
    Create a JWT access token with optional additional claims.

    Args:
        subject: The subject (usually user UUID) to encode in the token
        expires_delta: Optional custom expiration time
        additional_claims: Optional dict of additional claims to include

    Returns:
        Encoded JWT token string
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": now,
        "jti": str(uuid.uuid4()),  # JWT ID for token revocation support
    }

    if additional_claims:
        to_encode.update(additional_claims)

    encoded_jwt: str = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )  # type: ignore[no-any-return]
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        plain_password: The plaintext password to verify
        hashed_password: The stored password hash

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)  # type: ignore[no-any-return]


def verify_and_update_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, Optional[str]]:
    """
    Verify a password and optionally return an upgraded hash.

    This function supports automatic hash upgrade for FIPS compliance:
    - In FIPS mode: upgrades bcrypt/bcrypt_sha256 to PBKDF2-SHA256
    - In standard mode: upgrades plain bcrypt to bcrypt_sha256

    Args:
        plain_password: The plaintext password to verify
        hashed_password: The stored password hash

    Returns:
        Tuple of (is_valid, new_hash) where new_hash is None if no upgrade needed
    """
    is_valid, new_hash = pwd_context.verify_and_update(plain_password, hashed_password)
    return is_valid, new_hash


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be upgraded.

    This is useful for batch checking without requiring the plaintext password.

    Args:
        hashed_password: The stored password hash

    Returns:
        True if the hash uses a deprecated scheme and should be upgraded
    """
    return pwd_context.needs_update(hashed_password)  # type: ignore[no-any-return]


def get_password_hash(password: str) -> str:
    """
    Hash a password for storing
    """
    return pwd_context.hash(password)  # type: ignore[no-any-return]


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user by email and password.

    Note: LDAP users cannot authenticate via this function - they must use
    LDAP authentication. This function is for local users only.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    # LDAP users cannot authenticate via password - they have no local password
    if user.auth_type != "local":
        return None

    # Empty password hash means user cannot authenticate locally
    if not user.hashed_password:
        return None

    if not verify_password(password, str(user.hashed_password)):
        return None
    return user  # type: ignore[no-any-return]


def get_token_from_cookie(access_token: Optional[str] = Cookie(None)) -> str:
    """
    Extract the JWT token from the cookie
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return access_token


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify a JWT token and return its payload
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )  # type: ignore[no-any-return]
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
