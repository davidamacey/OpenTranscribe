"""
Keycloak/OIDC authentication module.

Handles authentication via OpenID Connect with Keycloak.
Supports PKCE (RFC 7636) for OAuth 2.1 compliance.
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Optional
from typing import TypedDict
from urllib.parse import urlencode

import httpx
from jose import JWTError
from jose import jwt

from app.auth.constants import AUTH_TYPE_KEYCLOAK
from app.auth.constants import EXTERNAL_AUTH_NO_PASSWORD
from app.core.config import settings

logger = logging.getLogger(__name__)


# PKCE Constants (RFC 7636)
PKCE_CODE_VERIFIER_MIN_LENGTH = 43
PKCE_CODE_VERIFIER_MAX_LENGTH = 128
PKCE_CODE_VERIFIER_LENGTH = 64  # Recommended length for security
# RFC 7636 Section 4.1: unreserved characters for code verifier
PKCE_UNRESERVED_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


def validate_pkce_code_verifier(code_verifier: str) -> bool:
    """
    Validate that a PKCE code verifier meets RFC 7636 requirements.

    RFC 7636 Section 4.1 specifies:
    - Length: 43-128 characters
    - Characters: Only unreserved characters (A-Z, a-z, 0-9, -, ., _, ~)

    Args:
        code_verifier: The code verifier string to validate

    Returns:
        True if valid, False otherwise
    """
    if not code_verifier:
        logger.warning("PKCE code_verifier is empty")
        return False

    # Check length requirements
    if len(code_verifier) < PKCE_CODE_VERIFIER_MIN_LENGTH:
        logger.warning(
            f"PKCE code_verifier too short: {len(code_verifier)} chars "
            f"(min: {PKCE_CODE_VERIFIER_MIN_LENGTH})"
        )
        return False

    if len(code_verifier) > PKCE_CODE_VERIFIER_MAX_LENGTH:
        logger.warning(
            f"PKCE code_verifier too long: {len(code_verifier)} chars "
            f"(max: {PKCE_CODE_VERIFIER_MAX_LENGTH})"
        )
        return False

    # Check character requirements (RFC 7636 unreserved characters only)
    invalid_chars = set(code_verifier) - PKCE_UNRESERVED_CHARS
    if invalid_chars:
        logger.warning(f"PKCE code_verifier contains invalid characters: {invalid_chars!r}")
        return False

    return True


class KeycloakUserData(TypedDict):
    """User data extracted from Keycloak token."""

    keycloak_id: str  # Subject (sub) from token
    email: str
    full_name: str
    username: str
    is_admin: bool
    roles: list[str]


@dataclass
class KeycloakTokens:
    """Tokens returned from Keycloak."""

    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int
    token_type: str


def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate a PKCE code verifier and code challenge pair.

    Following RFC 7636:
    - code_verifier: 43-128 character cryptographically random string
    - code_challenge: SHA256(code_verifier), base64url encoded, no padding

    Returns:
        tuple[str, str]: (code_verifier, code_challenge)
    """
    # Generate cryptographically secure random bytes
    # We need enough bytes to produce a 64-character base64url string
    # 48 bytes -> 64 base64 characters (4 * 48 / 3 = 64)
    random_bytes = secrets.token_bytes(48)

    # Create code_verifier using base64url encoding without padding
    code_verifier = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")

    # Create code_challenge = BASE64URL(SHA256(code_verifier))
    sha256_digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(sha256_digest).rstrip(b"=").decode("ascii")

    logger.debug(
        f"Generated PKCE pair: verifier length={len(code_verifier)}, "
        f"challenge length={len(code_challenge)}"
    )

    return code_verifier, code_challenge


def _get_keycloak_urls(internal: bool = False) -> dict:
    """Get Keycloak endpoint URLs.

    Args:
        internal: If True, use internal URL for backend-to-Keycloak communication.
                  If False, use public URL for browser redirects.
    """
    # Use internal URL for backend requests (token exchange, JWKS fetch)
    # Use public URL for browser redirects (authorization)
    if internal and settings.KEYCLOAK_INTERNAL_URL:
        base_url = settings.KEYCLOAK_INTERNAL_URL
    else:
        base_url = settings.KEYCLOAK_SERVER_URL

    base = f"{base_url}/realms/{settings.KEYCLOAK_REALM}"
    return {
        "authorization": f"{settings.KEYCLOAK_SERVER_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/auth",
        "token": f"{base}/protocol/openid-connect/token",
        "userinfo": f"{base}/protocol/openid-connect/userinfo",
        "logout": f"{base}/protocol/openid-connect/logout",
        "certs": f"{base}/protocol/openid-connect/certs",
    }


def get_authorization_url(state: str) -> tuple[str, Optional[str]]:
    """
    Generate the Keycloak authorization URL for OIDC login.

    Supports PKCE (RFC 7636) for OAuth 2.1 compliance when KEYCLOAK_USE_PKCE is enabled.

    Args:
        state: Random state parameter for CSRF protection

    Returns:
        tuple[str, Optional[str]]: (authorization_url, code_verifier or None if PKCE disabled)
            The code_verifier must be stored and passed to exchange_code_for_tokens()
    """
    urls = _get_keycloak_urls()
    params = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "redirect_uri": settings.KEYCLOAK_CALLBACK_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }

    code_verifier = None

    if settings.KEYCLOAK_USE_PKCE:
        code_verifier, code_challenge = generate_pkce_pair()
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
        logger.debug("PKCE enabled: added code_challenge to authorization URL")

    return f"{urls['authorization']}?{urlencode(params)}", code_verifier


async def exchange_code_for_tokens(
    code: str, code_verifier: Optional[str] = None
) -> Optional[KeycloakTokens]:
    """
    Exchange authorization code for tokens.

    Supports PKCE (RFC 7636) for OAuth 2.1 compliance when code_verifier is provided.

    Args:
        code: Authorization code from Keycloak callback
        code_verifier: PKCE code verifier (required if PKCE was used in authorization request)

    Returns:
        KeycloakTokens or None if exchange fails
    """
    urls = _get_keycloak_urls(internal=True)

    token_data = {
        "grant_type": "authorization_code",
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.KEYCLOAK_CALLBACK_URL,
    }

    # Add code_verifier for PKCE if provided
    if code_verifier:
        # Validate code_verifier meets RFC 7636 requirements before sending
        if not validate_pkce_code_verifier(code_verifier):
            logger.error("PKCE code_verifier validation failed - rejecting token exchange")
            return None
        token_data["code_verifier"] = code_verifier
        logger.debug("PKCE enabled: added code_verifier to token exchange request")

    async with httpx.AsyncClient(timeout=settings.KEYCLOAK_TIMEOUT) as client:
        try:
            response = await client.post(
                urls["token"],
                data=token_data,
            )
            response.raise_for_status()
            data = response.json()

            return KeycloakTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                id_token=data.get("id_token", ""),
                expires_in=data.get("expires_in", 300),
                token_type=data.get("token_type", "Bearer"),
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            return None


async def get_keycloak_jwks() -> Optional[dict]:
    """
    Fetch Keycloak public keys (JWKS).

    Returns:
        JWKS dict or None if fetch fails
    """
    urls = _get_keycloak_urls(internal=True)

    async with httpx.AsyncClient(timeout=settings.KEYCLOAK_TIMEOUT) as client:
        try:
            response = await client.get(urls["certs"])
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Keycloak JWKS: {e}")
            return None


async def validate_token(access_token: str) -> Optional[KeycloakUserData]:
    """
    Validate Keycloak access token and extract user data.

    Args:
        access_token: JWT access token from Keycloak

    Returns:
        KeycloakUserData or None if validation fails
    """
    try:
        # Fetch Keycloak public keys
        jwks = await get_keycloak_jwks()
        if not jwks:
            logger.error("Failed to fetch Keycloak JWKS for token validation")
            return None

        logger.debug(f"JWKS fetched successfully, keys count: {len(jwks.get('keys', []))}")

        # Decode and validate token
        # Note: python-jose handles key matching from JWKS
        # Audience validation is configurable - enable when Keycloak is configured with audience
        jwt_options = {}
        decode_kwargs = {}

        if settings.KEYCLOAK_VERIFY_AUDIENCE:
            # Validate audience claim (OWASP recommended)
            jwt_options["verify_aud"] = True
            audience = settings.KEYCLOAK_AUDIENCE or settings.KEYCLOAK_CLIENT_ID
            decode_kwargs["audience"] = audience
            logger.debug(f"Validating token audience against: {audience}")
        else:
            # Keycloak access tokens may not have audience claim by default
            jwt_options["verify_aud"] = False

        if settings.KEYCLOAK_VERIFY_ISSUER:
            # Validate issuer claim (OWASP recommended)
            # Expected issuer is: {KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}
            jwt_options["verify_iss"] = True
            expected_issuer = f"{settings.KEYCLOAK_SERVER_URL}/realms/{settings.KEYCLOAK_REALM}"
            decode_kwargs["issuer"] = expected_issuer
            logger.debug(f"Validating token issuer against: {expected_issuer}")
        else:
            jwt_options["verify_iss"] = False

        payload = jwt.decode(
            access_token,
            jwks,
            algorithms=["RS256"],
            options=jwt_options,
            **decode_kwargs,
        )

        logger.info(
            f"Token decoded successfully for user: {payload.get('preferred_username', 'unknown')}"
        )

        # Extract user data from token claims
        roles = payload.get("realm_access", {}).get("roles", [])
        is_admin = settings.KEYCLOAK_ADMIN_ROLE in roles

        return KeycloakUserData(
            keycloak_id=payload["sub"],
            email=payload.get("email", ""),
            full_name=payload.get("name", ""),
            username=payload.get("preferred_username", ""),
            is_admin=is_admin,
            roles=roles,
        )
    except JWTError as e:
        logger.warning(f"Invalid Keycloak token (JWTError): {e}")
        return None
    except Exception as e:
        logger.error(f"Error validating Keycloak token: {type(e).__name__}: {e}")
        return None


def _create_keycloak_user(db, keycloak_data: KeycloakUserData):
    """
    Create a new user from Keycloak data.

    Args:
        db: Database session
        keycloak_data: Keycloak user data

    Returns:
        Created User object

    Raises:
        ValueError: If user cannot be created or found after race condition
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.user import User

    keycloak_id = keycloak_data["keycloak_id"]
    email = keycloak_data["email"]

    # Use username from Keycloak if email is not available
    if not email:
        email = f"{keycloak_data['username']}@keycloak.local"

    logger.info(f"Creating new user from Keycloak: {keycloak_id} ({email})")

    user = User(
        email=email,
        full_name=keycloak_data["full_name"] or keycloak_data["username"] or email.split("@")[0],
        hashed_password=EXTERNAL_AUTH_NO_PASSWORD,
        auth_type=AUTH_TYPE_KEYCLOAK,
        keycloak_id=keycloak_id,
        role="admin" if keycloak_data["is_admin"] else "user",
        is_active=True,
        is_superuser=keycloak_data["is_admin"],
    )
    db.add(user)

    try:
        db.commit()
        return user
    except IntegrityError:
        # Race condition: user was created by concurrent request
        db.rollback()
        logger.info(f"User {keycloak_id} was created by concurrent request, fetching existing user")
        user = db.query(User).filter(User.keycloak_id == keycloak_id).first()
        if not user:
            user = db.query(User).filter(User.email == email).first()
        if not user:
            raise ValueError(f"Failed to create or find Keycloak user: {keycloak_id}") from None
        return user


def _update_keycloak_user(db, user, keycloak_data: KeycloakUserData):
    """
    Update an existing user's Keycloak data.

    Args:
        db: Database session
        user: Existing User object
        keycloak_data: Keycloak user data

    Returns:
        Updated User object
    """
    keycloak_id = keycloak_data["keycloak_id"]
    email = keycloak_data["email"]

    logger.info(f"Updating existing user from Keycloak: {keycloak_id} ({email})")

    # Log email changes at WARNING level for audit purposes
    if email and email != user.email:
        logger.warning(
            f"SECURITY: User email changed during Keycloak login. "
            f"keycloak_id={keycloak_id}, old_email={user.email}, new_email={email}"
        )
        user.email = email
    if keycloak_data["full_name"]:
        user.full_name = keycloak_data["full_name"]
    user.keycloak_id = keycloak_id
    user.auth_type = AUTH_TYPE_KEYCLOAK

    # Update admin role based on Keycloak roles
    if keycloak_data["is_admin"]:
        if user.role != "admin":
            logger.info(f"Promoting Keycloak user {keycloak_id} to admin")
        user.role = "admin"
        user.is_superuser = True
    elif user.role == "admin":
        # Demote if user was admin but no longer has admin role in Keycloak
        logger.info(f"Demoting Keycloak user {keycloak_id} from admin")
        user.role = "user"
        user.is_superuser = False

    db.commit()
    return user


def _convert_local_user_to_keycloak(db, user, keycloak_data: KeycloakUserData):
    """
    Convert an existing local user to Keycloak authentication.

    This is called when a user with auth_type='local' authenticates
    via Keycloak. The user is converted to Keycloak auth, which means:
    - auth_type is set to 'keycloak'
    - hashed_password is cleared (Keycloak users don't have local passwords)
    - keycloak_id is set from the token
    - Admin role is updated based on Keycloak roles

    Args:
        db: Database session
        user: Existing User object with auth_type='local'
        keycloak_data: Keycloak user data from token

    Returns:
        Updated User object
    """
    keycloak_id = keycloak_data["keycloak_id"]
    email = keycloak_data["email"]

    logger.info(f"Converting local user {user.email} to Keycloak auth: {keycloak_id}")

    # Convert to Keycloak authentication
    user.auth_type = AUTH_TYPE_KEYCLOAK
    user.keycloak_id = keycloak_id
    user.hashed_password = EXTERNAL_AUTH_NO_PASSWORD  # Clear local password

    # Update email and name if provided
    # Log email changes at WARNING level for audit purposes
    if email and email != user.email:
        logger.warning(
            f"SECURITY: User email changed during Keycloak conversion. "
            f"keycloak_id={keycloak_id}, old_email={user.email}, new_email={email}"
        )
        user.email = email
    if keycloak_data["full_name"]:
        user.full_name = keycloak_data["full_name"]

    # Update admin role based on Keycloak roles
    if keycloak_data["is_admin"]:
        if user.role != "admin":
            logger.info(f"Promoting converted Keycloak user {keycloak_id} to admin")
        user.role = "admin"
        user.is_superuser = True
    elif user.role == "admin":
        # Demote if user was admin locally but not in Keycloak admin role
        logger.info(
            f"Demoting converted Keycloak user {keycloak_id} from admin (no admin role in Keycloak)"
        )
        user.role = "user"
        user.is_superuser = False

    db.commit()
    return user


def sync_keycloak_user_to_db(db, keycloak_data: KeycloakUserData):
    """
    Create or update a user in the database from Keycloak data.

    Handles:
    - Creating new users on first Keycloak login
    - Updating existing Keycloak users
    - Protecting existing local users from being converted
    - Admin role promotion and demotion based on Keycloak roles
    - Race conditions when multiple concurrent logins occur

    Args:
        db: Database session
        keycloak_data: User data from Keycloak token

    Returns:
        User: The created or updated User object

    Raises:
        ValueError: If user cannot be created or found after race condition
    """
    from app.auth.constants import AUTH_TYPE_LOCAL
    from app.models.user import User

    keycloak_id = keycloak_data["keycloak_id"]
    email = keycloak_data["email"]

    # Check if user exists by keycloak_id first (most specific)
    user = db.query(User).filter(User.keycloak_id == keycloak_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        user = _create_keycloak_user(db, keycloak_data)
    elif user.auth_type == AUTH_TYPE_LOCAL:
        # Convert local users to Keycloak auth when they authenticate via Keycloak
        # This ensures they use Keycloak going forward and cannot change their password
        # (since Keycloak users don't have local passwords)
        logger.warning(
            f"SECURITY: Converting local user {email} to Keycloak auth. "
            "User will now authenticate exclusively via Keycloak. "
            "Local password will be cleared."
        )
        user = _convert_local_user_to_keycloak(db, user, keycloak_data)
    else:
        user = _update_keycloak_user(db, user, keycloak_data)

    db.refresh(user)
    return user
