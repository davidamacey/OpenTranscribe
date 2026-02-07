from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from app.schemas.base import UUIDBaseSchema


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user with password policy validation.

    Password validation is performed against the configured password policy
    when PASSWORD_POLICY_ENABLED is true. The policy enforces:
    - Minimum length (default: 12 characters)
    - Character complexity (uppercase, lowercase, digits, special chars)
    - No user information in password (email username, name parts)
    """

    password: str = Field(..., min_length=8)  # Base minimum for backward compatibility
    role: Optional[str] = "user"
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False

    @model_validator(mode="after")
    def validate_password_policy(self) -> "UserCreate":
        """Validate password against the configured password policy.

        This validator runs after all field validators, so we have access
        to both email and full_name for comprehensive validation.

        Raises:
            ValueError: If password doesn't meet policy requirements
        """
        from app.auth.password_policy import validate_password

        result = validate_password(
            password=self.password,
            email=self.email,
            full_name=self.full_name,
        )

        if not result.is_valid:
            # Combine all errors into a single message
            error_msg = "; ".join(result.errors)
            raise ValueError(f"Password does not meet policy requirements: {error_msg}")

        return self


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None  # For password change verification
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role: Optional[str] = None


class UserInDB(UserBase, UUIDBaseSchema):
    """User schema with UUID as public identifier"""

    role: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    is_superuser: bool
    auth_type: str  # "local", "ldap", "keycloak", "pki"
    ldap_uid: Optional[str] = None
    keycloak_id: Optional[str] = None
    pki_subject_dn: Optional[str] = None

    # FedRAMP compliance fields
    password_changed_at: Optional[datetime] = None
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    account_expires_at: Optional[datetime] = None


class User(UserInDB):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None  # Access token expiration in seconds


class TokenRefreshRequest(BaseModel):
    """Request body for token refresh endpoint."""

    refresh_token: str


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    jti: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None  # 'access' or 'refresh'


# ===== MFA Schemas (FedRAMP IA-2) =====


class MFASetupResponse(BaseModel):
    """Response from MFA setup initiation."""

    secret: str  # Base32-encoded TOTP secret (for manual entry)
    provisioning_uri: str  # otpauth:// URI for QR code
    qr_code_base64: str  # Base64-encoded PNG QR code image


class MFAVerifySetupRequest(BaseModel):
    """Request to verify MFA setup with initial TOTP code."""

    code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        """Ensure code contains only digits."""
        if not v.isdigit():
            raise ValueError("Code must contain only digits")
        return v


class MFAVerifySetupResponse(BaseModel):
    """Response from successful MFA setup verification."""

    success: bool
    backup_codes: list[str]  # One-time use backup codes (shown only once)
    message: str


class MFAVerifyRequest(BaseModel):
    """Request to verify MFA code during login."""

    mfa_token: str  # Short-lived token from initial login
    code: str = Field(
        ..., min_length=6, max_length=9, description="6-digit TOTP code or backup code (XXXX-XXXX)"
    )


class MFAVerifyResponse(BaseModel):
    """Response from successful MFA verification during login."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 spec constant, not a password
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class MFADisableRequest(BaseModel):
    """Request to disable MFA for current user."""

    code: str = Field(
        ..., min_length=6, max_length=9, description="6-digit TOTP code or backup code (XXXX-XXXX)"
    )


class MFAStatusResponse(BaseModel):
    """Response indicating MFA status for current user."""

    mfa_enabled: bool
    mfa_configured: bool  # True if user has started MFA setup
    mfa_required: bool  # True if system requires MFA
    can_setup_mfa: bool  # True if user can set up MFA (not PKI/Keycloak)


class MFALoginResponse(BaseModel):
    """Response when MFA is required during login."""

    mfa_required: bool = True
    mfa_token: str  # Short-lived token for MFA verification step
    message: str = "MFA verification required"


# ===== Login Banner Schemas (FedRAMP AC-8) =====


class LoginBannerResponse(BaseModel):
    """Response for login banner endpoint."""

    enabled: bool
    text: str
    classification: str
    requires_acknowledgment: bool


class BannerAcknowledgmentRequest(BaseModel):
    """Request to acknowledge login banner."""

    # No body required, user info comes from auth token


# ===== Admin Password Reset Schema =====


class AdminPasswordResetRequest(BaseModel):
    """Request body for admin-initiated password reset.

    Moving password from query parameter to request body prevents
    password exposure in server logs, browser history, and referrer headers.
    """

    new_password: str = Field(..., min_length=8, description="New password for the user")
    force_change: bool = Field(
        default=True, description="If true, user must change password on next login"
    )
