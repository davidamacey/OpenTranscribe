"""
Multi-Factor Authentication (MFA) service module.

Implements TOTP-based MFA following RFC 6238 (TOTP) and RFC 4226 (HOTP).
Compliant with FedRAMP IA-2 multi-factor authentication requirements.

Features:
- TOTP secret generation using cryptographically secure random bytes
- QR code provisioning URI generation for authenticator apps
- TOTP verification with configurable time window
- One-time use backup codes with secure hashing (bcrypt)
- TOTP secrets encrypted at rest using Fernet (AES-128-CBC)

Security:
- TOTP secrets are encrypted before storage and decrypted on verification
- Backup codes are hashed with bcrypt (cost factor 12) for resistance to brute-force
"""

import base64
import io
import logging
import secrets
from typing import Optional

import pyotp
import qrcode
from passlib.context import CryptContext

from app.core.config import settings
from app.utils.encryption import decrypt_api_key
from app.utils.encryption import encrypt_api_key

logger = logging.getLogger(__name__)

# Bcrypt context for backup code hashing
# Using cost factor 12 for balance between security and performance
# Backup codes are 8 chars, so bcrypt provides good protection against brute-force
backup_code_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


class MFAService:
    """
    Service for handling TOTP-based Multi-Factor Authentication.

    Implements RFC 6238 TOTP with 30-second time step and SHA-1 algorithm
    (standard for Google Authenticator compatibility).
    """

    # TOTP configuration
    TOTP_DIGITS = 6  # Standard 6-digit codes
    TOTP_INTERVAL = 30  # 30-second time step (RFC 6238 default)
    TOTP_VALID_WINDOW = 1  # Allow 1 step before/after for clock drift

    # Backup code configuration
    BACKUP_CODE_LENGTH = 8  # 8 character backup codes
    BACKUP_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Exclude ambiguous chars

    @staticmethod
    def generate_totp_secret() -> str:
        """
        Generate a new TOTP secret using cryptographically secure random bytes.

        Returns a base32-encoded secret suitable for TOTP authentication.
        The secret is 160 bits (20 bytes) per RFC 4226 recommendation.

        Returns:
            str: Base32-encoded TOTP secret (plaintext, must be encrypted before storage)
        """
        # Generate 20 bytes (160 bits) of random data
        random_bytes = secrets.token_bytes(20)
        # Encode as base32 (standard for TOTP secrets)
        secret = base64.b32encode(random_bytes).decode("utf-8")
        logger.debug("Generated new TOTP secret")
        return secret

    @staticmethod
    def encrypt_totp_secret(secret: str) -> str:
        """
        Encrypt a TOTP secret for secure storage at rest.

        Uses Fernet symmetric encryption (AES-128-CBC) with the application's
        ENCRYPTION_KEY. This ensures TOTP secrets are not stored in plaintext.

        Args:
            secret: Base32-encoded TOTP secret (plaintext)

        Returns:
            str: Encrypted TOTP secret (base64-encoded)

        Raises:
            ValueError: If encryption fails
        """
        encrypted = encrypt_api_key(secret)
        if encrypted is None:
            logger.error("Failed to encrypt TOTP secret")
            raise ValueError("Failed to encrypt TOTP secret")
        logger.debug("TOTP secret encrypted for storage")
        return encrypted

    @staticmethod
    def decrypt_totp_secret(encrypted_secret: str) -> str:
        """
        Decrypt a TOTP secret from storage.

        Args:
            encrypted_secret: Encrypted TOTP secret from database

        Returns:
            str: Decrypted base32-encoded TOTP secret

        Raises:
            ValueError: If decryption fails
        """
        decrypted = decrypt_api_key(encrypted_secret)
        if decrypted is None:
            logger.error("Failed to decrypt TOTP secret")
            raise ValueError("Failed to decrypt TOTP secret")
        logger.debug("TOTP secret decrypted for verification")
        return decrypted

    @staticmethod
    def get_provisioning_uri(secret: str, email: str, issuer_name: Optional[str] = None) -> str:
        """
        Generate a provisioning URI for authenticator apps.

        The URI follows the otpauth:// format specified in Google Authenticator's
        key URI format specification.

        Args:
            secret: Base32-encoded TOTP secret
            email: User's email address (used as account name)
            issuer_name: Name of the issuer (defaults to settings.MFA_ISSUER_NAME)

        Returns:
            str: otpauth:// URI for QR code generation
        """
        issuer = issuer_name or settings.MFA_ISSUER_NAME
        totp = pyotp.TOTP(secret, digits=MFAService.TOTP_DIGITS, interval=MFAService.TOTP_INTERVAL)
        uri: str = totp.provisioning_uri(name=email, issuer_name=issuer)  # type: ignore[no-any-return]
        logger.debug(f"Generated provisioning URI for user: {email[:3]}***")
        return uri

    @staticmethod
    def generate_qr_code_base64(provisioning_uri: str) -> str:
        """
        Generate a QR code image as a base64-encoded PNG.

        Args:
            provisioning_uri: The otpauth:// URI to encode

        Returns:
            str: Base64-encoded PNG image data (without data URI prefix)
        """
        # Create QR code with high error correction
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        # Generate PNG image using PIL (installed via qrcode[pil])
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.debug("Generated QR code for MFA setup")
        return img_base64

    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        """
        Verify a TOTP code against the secret.

        Allows for a configurable time window to account for clock drift
        between the server and the user's device.

        Args:
            secret: Base32-encoded TOTP secret
            code: 6-digit TOTP code from user

        Returns:
            bool: True if the code is valid, False otherwise
        """
        if not code or not secret:
            return False

        # Clean the code (remove spaces/dashes if any)
        code = code.replace(" ", "").replace("-", "")

        # Validate code format
        if not code.isdigit() or len(code) != MFAService.TOTP_DIGITS:
            logger.warning("Invalid TOTP code format")
            return False

        try:
            totp = pyotp.TOTP(
                secret, digits=MFAService.TOTP_DIGITS, interval=MFAService.TOTP_INTERVAL
            )
            # verify() accepts valid_window parameter for clock drift tolerance
            is_valid: bool = totp.verify(code, valid_window=MFAService.TOTP_VALID_WINDOW)  # type: ignore[no-any-return]

            if is_valid:
                logger.debug("TOTP verification successful")
            else:
                logger.debug("TOTP verification failed - invalid code")

            return is_valid
        except Exception as e:
            logger.error(f"TOTP verification error: {str(e)}")
            return False

    @staticmethod
    def generate_backup_codes(count: Optional[int] = None) -> list[str]:
        """
        Generate one-time use backup codes.

        Backup codes are randomly generated using a restricted alphabet
        that excludes ambiguous characters (0, O, I, 1, L).

        Args:
            count: Number of backup codes to generate (defaults to settings.MFA_BACKUP_CODE_COUNT)

        Returns:
            list[str]: List of plaintext backup codes
        """
        num_codes = count or settings.MFA_BACKUP_CODE_COUNT
        codes = []

        for _ in range(num_codes):
            # Generate random code using secure random choice
            code = "".join(
                secrets.choice(MFAService.BACKUP_CODE_ALPHABET)
                for _ in range(MFAService.BACKUP_CODE_LENGTH)
            )
            # Format as XXXX-XXXX for readability
            formatted_code = f"{code[:4]}-{code[4:]}"
            codes.append(formatted_code)

        logger.debug(f"Generated {num_codes} backup codes")
        return codes

    @staticmethod
    def hash_backup_code(code: str) -> str:
        """
        Hash a backup code for secure storage using bcrypt.

        Uses bcrypt with cost factor 12 for resistance to brute-force attacks.
        Backup codes are 8 characters, making bcrypt appropriate for this use case.

        Args:
            code: Plaintext backup code

        Returns:
            str: Bcrypt hash of the normalized backup code
        """
        # Normalize: remove formatting, uppercase
        normalized = code.replace("-", "").replace(" ", "").upper()
        # Hash with bcrypt (cost factor 12)
        return backup_code_context.hash(normalized)  # type: ignore[no-any-return]

    @staticmethod
    def verify_backup_code(code: str, hashed_codes: list[str]) -> tuple[bool, Optional[str]]:
        """
        Verify a backup code against a list of bcrypt-hashed codes.

        Uses constant-time comparison via passlib to prevent timing attacks.

        Args:
            code: Plaintext backup code from user
            hashed_codes: List of bcrypt-hashed backup codes

        Returns:
            tuple[bool, Optional[str]]: (is_valid, matched_hash)
                - is_valid: True if code matches one of the hashed codes
                - matched_hash: The hash that matched (for removal), or None if invalid
        """
        if not code or not hashed_codes:
            return False, None

        # Normalize the provided code
        normalized = code.replace("-", "").replace(" ", "").upper()

        # Check against each stored hash using bcrypt verify
        for stored_hash in hashed_codes:
            try:
                if backup_code_context.verify(normalized, stored_hash):
                    logger.info("Backup code verification successful")
                    return True, stored_hash
            except Exception as e:
                # Handle potential invalid hash format (e.g., legacy SHA-256 hashes)
                logger.debug(f"Backup code hash verification error: {e}")
                continue

        logger.debug("Backup code verification failed - code not found")
        return False, None

    @staticmethod
    def hash_backup_codes(codes: list[str]) -> list[str]:
        """
        Hash a list of backup codes for storage using bcrypt.

        Args:
            codes: List of plaintext backup codes

        Returns:
            list[str]: List of bcrypt-hashed backup codes
        """
        return [MFAService.hash_backup_code(code) for code in codes]
