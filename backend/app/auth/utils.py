"""Shared authentication utility functions.

Provides common helpers used across multiple auth modules to avoid
code duplication.
"""


def mask_identifier(identifier: str) -> str:
    """Mask identifier for safe logging to prevent sensitive data exposure.

    For emails (contains @): shows first char + *** + @domain
        e.g., "john.doe@example.com" -> "j***@example.com"
    For usernames: shows first 2 chars + ***
        e.g., "johndoe" -> "jo***"

    Args:
        identifier: Email or username to mask

    Returns:
        Masked identifier string
    """
    if not identifier:
        return "***"

    identifier = identifier.strip()

    if "@" in identifier:
        # Email format: show first char + *** + @domain
        local_part, domain = identifier.split("@", 1)
        if len(local_part) >= 1:
            return f"{local_part[0]}***@{domain}"
        return f"***@{domain}"
    else:
        # Username format: show first 2 chars + ***
        if len(identifier) >= 2:
            return f"{identifier[:2]}***"
        elif len(identifier) == 1:
            return f"{identifier[0]}***"
        return "***"
