"""
Encryption utilities for secure storage of sensitive data like API keys.

Uses Fernet symmetric encryption to encrypt/decrypt sensitive information.
"""

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """
    Get or generate encryption key from settings.

    Returns:
        bytes: Encryption key for Fernet cipher

    Raises:
        ValueError: If encryption key is invalid
    """
    try:
        # Use the encryption key from settings
        key_string = settings.ENCRYPTION_KEY

        # If it's already a valid Fernet key, use it
        try:
            return base64.urlsafe_b64decode(key_string)
        except Exception:
            # If not a valid base64 key, derive from string
            # This creates a consistent key from the string
            key_material = key_string.encode("utf-8")
            # Pad or truncate to 32 bytes
            if len(key_material) < 32:
                key_material = key_material.ljust(32, b"\0")
            else:
                key_material = key_material[:32]

            # Encode as base64url for Fernet
            return base64.urlsafe_b64encode(key_material)
    except Exception as e:
        logger.error(f"Failed to get encryption key: {e}")
        raise ValueError("Invalid encryption key configuration")


def encrypt_api_key(api_key: str) -> Optional[str]:
    """
    Encrypt an API key for secure storage.

    Args:
        api_key: Plain text API key to encrypt

    Returns:
        Encrypted API key as base64 string, or None if encryption fails
    """
    if not api_key or not api_key.strip():
        return None

    try:
        key = _get_encryption_key()
        fernet = Fernet(key)

        # Encrypt the API key
        encrypted_data = fernet.encrypt(api_key.encode("utf-8"))

        # Return as base64 string for storage
        return base64.urlsafe_b64encode(encrypted_data).decode("ascii")

    except Exception as e:
        logger.error(f"Failed to encrypt API key: {e}")
        return None


def decrypt_api_key(encrypted_api_key: str) -> Optional[str]:
    """
    Decrypt an API key from storage.

    Args:
        encrypted_api_key: Encrypted API key from database

    Returns:
        Decrypted API key as plain text, or None if decryption fails
    """
    if not encrypted_api_key or not encrypted_api_key.strip():
        return None

    try:
        key = _get_encryption_key()
        fernet = Fernet(key)

        # Decode from base64
        encrypted_data = base64.urlsafe_b64decode(encrypted_api_key.encode("ascii"))

        # Decrypt and return as string
        decrypted_data = fernet.decrypt(encrypted_data)
        return decrypted_data.decode("utf-8")

    except Exception as e:
        logger.error(f"Failed to decrypt API key: {e}")
        return None


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    This can be used to generate a secure encryption key for production use.

    Returns:
        Base64-encoded encryption key suitable for ENCRYPTION_KEY environment variable
    """
    key = Fernet.generate_key()
    return key.decode("ascii")


def test_encryption() -> bool:
    """
    Test encryption/decryption functionality.

    Returns:
        True if encryption is working correctly, False otherwise
    """
    try:
        test_data = "test_api_key_12345"

        # Test encryption
        encrypted = encrypt_api_key(test_data)
        if not encrypted:
            return False

        # Test decryption
        decrypted = decrypt_api_key(encrypted)
        if decrypted != test_data:
            return False

        return True

    except Exception as e:
        logger.error(f"Encryption test failed: {e}")
        return False


# Utility functions for common patterns
def encrypt_if_not_empty(value: Optional[str]) -> Optional[str]:
    """
    Encrypt a value only if it's not empty.

    Args:
        value: Value to encrypt (can be None or empty)

    Returns:
        Encrypted value or None
    """
    if not value or not value.strip():
        return None
    return encrypt_api_key(value)


def decrypt_if_not_empty(value: Optional[str]) -> Optional[str]:
    """
    Decrypt a value only if it's not empty.

    Args:
        value: Encrypted value to decrypt (can be None or empty)

    Returns:
        Decrypted value or None
    """
    if not value or not value.strip():
        return None
    return decrypt_api_key(value)
