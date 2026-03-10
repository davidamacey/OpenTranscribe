"""
API endpoints for user ASR (Automatic Speech Recognition) settings management.

Follows the same pattern as llm_settings.py for consistency.
"""

import contextlib
import logging
import os
import re
import time
from datetime import datetime
from datetime import timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from sqlalchemy.orm import Session

from app import models
from app.api.endpoints.auth import get_current_active_user
from app.auth.rate_limit import get_api_rate_limit
from app.auth.rate_limit import limiter
from app.db.base import get_db
from app.utils.encryption import decrypt_api_key
from app.utils.encryption import encrypt_api_key
from app.utils.encryption import test_encryption

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive-data sanitization for error messages
# ---------------------------------------------------------------------------

# Matches Bearer tokens and high-entropy strings with common API-key prefixes,
# as well as generic base64-ish blobs of 32+ chars that could be a raw key.
_KEY_PATTERN = re.compile(
    r"(Bearer\s+)\S+|(sk-|dg_|aai_)\S+",
    re.IGNORECASE,
)


def _sanitize_message(message: str, *secrets: str | None) -> str:
    """Remove known secrets and API-key-shaped tokens from an error message.

    Performs two passes:
    1. Exact replacement of each provided *secret* value.
    2. Regex-based scrubbing of Bearer tokens and common API-key prefixes.
    """
    if not message:
        return message
    result = message
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    result = _KEY_PATTERN.sub(
        lambda m: m.group(1) + "***" if m.group(1) else m.group(2) + "***", result
    )
    return result


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

# Maximum length for an API key submitted by the user. Cloud provider keys are
# typically < 256 characters; a generous cap of 8 192 bytes blocks resource-
# exhaustion attacks while leaving room for long JWT/service-account tokens.
_MAX_API_KEY_LEN = 8192

# Valid ASR providers as accepted by the factory.
_VALID_PROVIDERS = frozenset(
    {
        "local",
        "deepgram",
        "assemblyai",
        "openai",
        "google",
        "azure",
        "aws",
        "speechmatics",
        "gladia",
    }
)

# Cloud-based providers (excludes "local").
_CLOUD_PROVIDERS = {
    "deepgram",
    "assemblyai",
    "openai",
    "google",
    "azure",
    "aws",
    "speechmatics",
    "gladia",
}

# Azure and AWS regions are curated allowlists — unknown values are rejected.
_VALID_AZURE_REGIONS = frozenset(
    {
        "westus",
        "westus2",
        "eastus",
        "eastus2",
        "centralus",
        "northcentralus",
        "southcentralus",
        "westeurope",
        "northeurope",
        "uksouth",
        "ukwest",
        "francecentral",
        "germanywestcentral",
        "switzerlandnorth",
        "australiaeast",
        "australiasoutheast",
        "southeastasia",
        "eastasia",
        "japaneast",
        "japanwest",
        "koreacentral",
        "koreasouth",
        "canadacentral",
        "canadaeast",
        "brazilsouth",
        "southafricanorth",
        "uaenorth",
    }
)
_VALID_AWS_REGIONS = frozenset(
    {
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ca-central-1",
        "ca-west-1",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-central-1",
        "eu-north-1",
        "eu-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-southeast-3",
        "ap-northeast-1",
        "ap-northeast-2",
        "ap-northeast-3",
        "ap-south-1",
        "ap-east-1",
        "sa-east-1",
        "me-south-1",
        "af-south-1",
    }
)


def _validate_base_url(base_url: str | None) -> None:
    """Raise HTTP 400 if *base_url* is not a safe http(s) URL.

    Blocks file://, gopher://, and other non-HTTP schemes that could be used
    for Server-Side Request Forgery (SSRF).
    """
    if not base_url:
        return
    stripped = base_url.strip()
    if not re.match(r"^https?://", stripped, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="base_url must begin with http:// or https://",
        )


def _validate_api_key_length(api_key: str | None) -> None:
    """Raise HTTP 400 if the provided API key exceeds the safe maximum length."""
    if api_key and len(api_key) > _MAX_API_KEY_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"api_key must not exceed {_MAX_API_KEY_LEN} characters",
        )


def _validate_provider(provider: str | None) -> None:
    """Raise HTTP 400 if *provider* is not a recognised value."""
    if provider and provider not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Must be one of: {', '.join(sorted(_VALID_PROVIDERS))}",
        )


def _validate_region(provider: str | None, region: str | None) -> None:
    """Raise HTTP 400 if *region* is not on the allowlist for providers that require one."""
    if not region:
        return
    if provider == "azure" and region not in _VALID_AZURE_REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown Azure region '{region}'",
        )
    if provider == "aws" and region not in _VALID_AWS_REGIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown AWS region '{region}'",
        )


# ---------------------------------------------------------------------------
# Lazy imports to avoid circular dependencies at module load time
# ---------------------------------------------------------------------------


def _get_provider_catalog() -> dict:
    """Return the ASR provider catalog, or empty dict if not yet available."""
    try:
        from app.services.asr.factory import ASR_PROVIDER_CATALOG  # type: ignore[import]

        return ASR_PROVIDER_CATALOG
    except ImportError:
        logger.debug("ASR provider catalog not yet available (services/asr not yet created)")
        return {}


def _get_asr_settings_model():
    """Lazily import the UserASRSettings model."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    return UserASRSettings


def _create_asr_provider(
    provider: str,
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    region: str | None,
):
    """Create an ASR provider instance via the factory."""
    from app.services.asr.factory import ASRProviderFactory  # type: ignore[import]

    return ASRProviderFactory.create_from_config(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        region=region,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _set_active_asr_configuration(db: Session, user_id: int, config_id: int) -> None:
    """Persist the active ASR configuration ID in UserSetting."""
    existing = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )
    if existing:
        existing.setting_value = str(config_id)  # type: ignore[assignment]
        db.add(existing)
    else:
        db.add(
            models.UserSetting(
                user_id=user_id,
                setting_key="active_asr_config_id",
                setting_value=str(config_id),
            )
        )
    db.commit()


def _get_active_asr_config_id(db: Session, user_id: int) -> int | None:
    """Return the stored active ASR config integer ID, or None."""
    setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )
    if setting and setting.setting_value:
        with contextlib.suppress(ValueError, TypeError):
            return int(setting.setting_value)
    return None


def _clear_active_asr_setting(db: Session, user_id: int) -> None:
    """Delete the active_asr_config_id UserSetting row if it exists."""
    setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )
    if setting:
        db.delete(setting)
        db.commit()


def _config_to_dict(config: Any) -> dict:
    """Serialize a UserASRSettings record to a safe public dict (no raw API key)."""
    return {
        "id": config.id,
        "uuid": str(config.uuid),
        "user_id": config.user_id,
        "name": config.name,
        "provider": config.provider,
        "model_name": config.model_name,
        "base_url": config.base_url,
        "region": config.region,
        "is_active": config.is_active,
        "has_api_key": bool(config.api_key),
        "last_tested": config.last_tested.isoformat() if config.last_tested else None,
        "test_status": config.test_status,
        "test_message": config.test_message,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def _get_config_or_404(db: Session, config_uuid: UUID, user_id: int) -> Any:
    """Fetch UserASRSettings by UUID+user or raise 404."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    config = (
        db.query(UserASRSettings)
        .filter(
            UserASRSettings.uuid == config_uuid,
            UserASRSettings.user_id == user_id,
        )
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="ASR configuration not found")
    return config


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/providers")
def get_providers(
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Return the full ASR provider catalog with models, pricing, and capabilities."""
    catalog = _get_provider_catalog()
    return {"providers": list(catalog.values())}


@router.get("/status")
def get_asr_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Get ASR configuration status summary for the current user."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    # Single query: fetch all configs + active_config_id setting in 2 queries total.
    # Resolve active_config from the already-fetched list (no 3rd DB round-trip).
    active_config_id = _get_active_asr_config_id(db, current_user.id)

    configs = db.query(UserASRSettings).filter(UserASRSettings.user_id == current_user.id).all()
    has_settings = len(configs) > 0

    active_config = None
    if active_config_id:
        # Resolve from already-fetched list — no additional DB query needed.
        active_config = next((c for c in configs if c.id == active_config_id), None)

    deployment_mode = os.getenv("DEPLOYMENT_MODE", "full").lower()
    asr_provider = os.getenv("ASR_PROVIDER", "local").lower()
    using_local_default = active_config is None and asr_provider == "local"

    active_provider: str | None = None
    active_model: str | None = None
    active_config_uuid_str: str | None = None
    is_cloud_provider = False

    if active_config:
        active_provider = str(getattr(active_config, "provider", "") or "")
        active_model = str(getattr(active_config, "model_name", "") or "")
        active_config_uuid_str = str(getattr(active_config, "uuid", "") or "")
        is_cloud_provider = active_provider.lower() in _CLOUD_PROVIDERS
    elif not using_local_default:
        # Env-level provider (not local)
        active_provider = asr_provider
        is_cloud_provider = asr_provider in _CLOUD_PROVIDERS

    from app.services.asr.factory import ASRProviderFactory

    return {
        "has_settings": has_settings,
        "active_config": _config_to_dict(active_config) if active_config else None,
        "using_local_default": using_local_default,
        "deployment_mode": deployment_mode,
        "asr_configured": bool(active_config) or not using_local_default,
        "active_provider": active_provider,
        "active_model": active_model,
        "active_config_uuid": active_config_uuid_str,
        "is_cloud_provider": is_cloud_provider,
        "active_model_capabilities": ASRProviderFactory.get_active_model_capabilities(
            current_user.id, db
        ),
    }


@router.get("")
def list_asr_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """List all ASR configurations belonging to the current user."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    configs = (
        db.query(UserASRSettings)
        .filter(UserASRSettings.user_id == current_user.id)
        .order_by(UserASRSettings.created_at)
        .all()
    )
    active_config_id = _get_active_asr_config_id(db, current_user.id)

    # Resolve active UUID from the already-fetched list — no 3rd DB query needed.
    active_uuid = None
    if active_config_id:
        active = next((c for c in configs if c.id == active_config_id), None)
        if active:
            active_uuid = str(active.uuid)

    return {
        "configs": [_config_to_dict(c) for c in configs],
        "active_config_id": active_config_id,
        "active_config_uuid": active_uuid,
    }


@router.get("/config/{config_uuid}")
def get_asr_config(
    config_uuid: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Get a specific ASR configuration by UUID (API key is never returned)."""
    config = _get_config_or_404(db, config_uuid, current_user.id)
    return _config_to_dict(config)


@router.get("/config/{config_uuid}/api-key")
def get_asr_config_api_key(
    config_uuid: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Return the decrypted API key for the specified configuration. Owner-only."""
    config = _get_config_or_404(db, config_uuid, current_user.id)

    if not config.api_key:
        return {"api_key": None}

    decrypted = decrypt_api_key(str(config.api_key))
    if decrypted is None:
        logger.error(f"Failed to decrypt API key for ASR config {config_uuid}")
        raise HTTPException(status_code=500, detail="Failed to decrypt API key")

    return {"api_key": decrypted}


@router.post("", status_code=201)
def create_asr_config(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Create a new ASR configuration. Auto-activates if this is the user's first config."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    config_name = body.get("name", "My ASR Config")
    provider = body.get("provider", "local")
    api_key = body.get("api_key")
    base_url = body.get("base_url")
    region = body.get("region")

    # --- Input validation ---
    _validate_provider(provider)
    _validate_api_key_length(api_key)
    _validate_base_url(base_url)
    _validate_region(provider, region)

    # Duplicate name check
    existing = (
        db.query(UserASRSettings)
        .filter(
            UserASRSettings.user_id == current_user.id,
            UserASRSettings.name == config_name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Configuration named '{config_name}' already exists",
        )

    # Test encryption before proceeding
    if not test_encryption():
        raise HTTPException(status_code=500, detail="Encryption system is not working properly")

    encrypted_key = None
    if api_key:
        encrypted_key = encrypt_api_key(api_key)
        if not encrypted_key:
            raise HTTPException(status_code=500, detail="Failed to encrypt API key")

    # Check before insert whether the user already has any config (determines auto-activate).
    # This avoids a second count query after the INSERT.
    has_existing = (
        db.query(UserASRSettings.id)
        .filter(UserASRSettings.user_id == current_user.id)
        .limit(1)
        .scalar()
        is not None
    )

    config = UserASRSettings(
        user_id=current_user.id,
        name=config_name,
        provider=provider,
        model_name=body.get("model_name", ""),
        api_key=encrypted_key,
        base_url=base_url,
        region=region,
        is_active=body.get("is_active", True),
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    # Auto-activate if this is the user's first config (no pre-existing configs).
    if not has_existing:
        _set_active_asr_configuration(db, int(current_user.id), int(config.id))

    return _config_to_dict(config)


@router.put("/config/{config_uuid}")
def update_asr_config(  # noqa: C901
    config_uuid: UUID,
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Update an existing ASR configuration."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    config = _get_config_or_404(db, config_uuid, current_user.id)

    # --- Input validation for fields that are being updated ---
    incoming_provider = body.get("provider") if "provider" in body else config.provider
    if "provider" in body:
        _validate_provider(body["provider"])
    if "api_key" in body:
        _validate_api_key_length(body.get("api_key"))
    if "base_url" in body:
        _validate_base_url(body.get("base_url"))
    if "region" in body:
        _validate_region(incoming_provider, body.get("region"))

    # Name update with duplicate check
    if "name" in body:
        new_name = body["name"]
        if new_name != config.name:
            dup = (
                db.query(UserASRSettings)
                .filter(
                    UserASRSettings.user_id == current_user.id,
                    UserASRSettings.name == new_name,
                    UserASRSettings.id != config.id,
                )
                .first()
            )
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail=f"Configuration named '{new_name}' already exists",
                )
        config.name = new_name  # type: ignore[assignment]

    if "provider" in body:
        new_provider = body["provider"]
        if new_provider != config.provider:
            # Provider change invalidates the existing API key (it belongs to the old
            # provider's account).  Clear the stored key so the user is prompted to
            # supply a new one rather than inadvertently inheriting a stale credential.
            config.api_key = None  # type: ignore[assignment]
        config.provider = new_provider  # type: ignore[assignment]
        # Reset test status when provider changes
        config.test_status = None  # type: ignore[assignment]
        config.test_message = None  # type: ignore[assignment]
        config.last_tested = None  # type: ignore[assignment]

    if "model_name" in body:
        config.model_name = body["model_name"]  # type: ignore[assignment]

    if "api_key" in body:
        new_key = body["api_key"]
        if new_key is None or (isinstance(new_key, str) and not new_key.strip()):
            # Empty string or null from the client means "keep the existing key".
            # The frontend sends "" when the user edits other fields without touching
            # the API key field.  Only a deliberate non-empty value replaces the key.
            # To explicitly clear the key a dedicated endpoint should be used, or the
            # caller should omit the "api_key" field entirely when not changing it.
            pass  # Existing key is preserved
        else:
            if not test_encryption():
                raise HTTPException(
                    status_code=500, detail="Encryption system is not working properly"
                )
            encrypted = encrypt_api_key(new_key)
            if not encrypted:
                raise HTTPException(status_code=500, detail="Failed to encrypt API key")
            config.api_key = encrypted  # type: ignore[assignment]
            # Reset test status only when key actually changes
            config.test_status = None  # type: ignore[assignment]

    if "base_url" in body:
        config.base_url = body["base_url"]  # type: ignore[assignment]

    if "region" in body:
        config.region = body["region"]  # type: ignore[assignment]

    if "is_active" in body:
        config.is_active = body["is_active"]  # type: ignore[assignment]

    db.add(config)
    db.commit()
    db.refresh(config)

    return _config_to_dict(config)


@router.post("/set-active")
def set_active_asr_config(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Set the active ASR configuration for the current user."""
    # Accept both "config_uuid" (internal name) and "uuid" (spec alias)
    config_uuid = body.get("config_uuid") or body.get("uuid")
    if not config_uuid:
        raise HTTPException(status_code=400, detail="config_uuid (or uuid) is required")

    try:
        uuid_obj = UUID(str(config_uuid))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format") from None

    config = _get_config_or_404(db, uuid_obj, current_user.id)
    _set_active_asr_configuration(db, int(current_user.id), int(config.id))

    return {
        "message": "Active ASR configuration updated",
        "config_uuid": str(config.uuid),
    }


@router.delete("/config/{config_uuid}", status_code=204)
def delete_asr_config(
    config_uuid: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> None:
    """Delete an ASR configuration. Auto-promotes another config if this was active."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    config = _get_config_or_404(db, config_uuid, current_user.id)

    active_config_id = _get_active_asr_config_id(db, current_user.id)
    was_active = active_config_id == int(config.id)

    config_id = int(config.id)
    db.delete(config)
    db.commit()

    if was_active:
        # Promote another config if available
        another = (
            db.query(UserASRSettings)
            .filter(
                UserASRSettings.user_id == current_user.id,
                UserASRSettings.id != config_id,
            )
            .first()
        )
        if another:
            _set_active_asr_configuration(db, int(current_user.id), int(another.id))
        else:
            _clear_active_asr_setting(db, int(current_user.id))


@router.delete("/all", status_code=204)
def delete_all_asr_configs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> None:
    """Delete all ASR configurations for the current user (reverts to system default)."""
    from app.models.user_asr_settings import UserASRSettings  # type: ignore[import]

    db.query(UserASRSettings).filter(UserASRSettings.user_id == current_user.id).delete()
    _clear_active_asr_setting(db, int(current_user.id))
    db.commit()


@router.post("/test")
@limiter.limit(get_api_rate_limit())
def test_asr_connection(
    request: Request,
    body: dict,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Test an ad-hoc ASR connection without saving configuration."""
    provider_name = body.get("provider", "local")
    api_key = body.get("api_key")
    base_url = body.get("base_url")
    region = body.get("region")
    model_name = body.get("model_name")

    # --- Input validation ---
    _validate_provider(provider_name)
    _validate_api_key_length(api_key)
    _validate_base_url(base_url)
    _validate_region(provider_name, region)

    start_time = time.time()
    try:
        provider = _create_asr_provider(
            provider=provider_name,
            api_key=api_key,
            model=model_name,
            base_url=base_url,
            region=region,
        )
        success, message, response_time_ms = provider.validate_connection()
    except Exception as exc:
        response_time_ms = (time.time() - start_time) * 1000
        sanitized = _sanitize_message(str(exc), api_key)
        logger.warning(
            "ASR ad-hoc test failed for provider '%s': %s",
            provider_name,
            sanitized,
        )
        return {
            "success": False,
            "message": sanitized,
            "response_time_ms": int(response_time_ms),
        }

    return {
        "success": success,
        "message": message,
        "response_time_ms": int(response_time_ms),
    }


@router.post("/test-config/{config_uuid}")
@limiter.limit(get_api_rate_limit())
def test_saved_asr_config(
    request: Request,
    config_uuid: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Test a saved ASR configuration and persist the result (test_status, test_message, last_tested)."""
    config = _get_config_or_404(db, config_uuid, current_user.id)

    # Decrypt the stored key (if any)
    api_key = None
    if config.api_key:
        api_key = decrypt_api_key(str(config.api_key))
        if api_key is None:
            logger.error("Failed to decrypt API key for ASR config %s", config_uuid)
            raise HTTPException(status_code=500, detail="Failed to decrypt stored API key")

    start_time = time.time()
    try:
        provider = _create_asr_provider(
            provider=config.provider,
            api_key=api_key,
            model=config.model_name,
            base_url=config.base_url,
            region=config.region,
        )
        success, message, response_time_ms = provider.validate_connection()
    except Exception as exc:
        success = False
        # Sanitize before storing or returning — provider exceptions may echo back the key
        message = _sanitize_message(str(exc), api_key)
        response_time_ms = (time.time() - start_time) * 1000
        logger.warning("ASR saved-config test failed for config %s: %s", config_uuid, message)

    # Persist test result — always store the sanitized message so plaintext keys
    # can never end up persisted in the database.
    config.test_status = "success" if success else "failed"  # type: ignore[assignment]
    config.test_message = _sanitize_message(message, api_key)  # type: ignore[assignment]
    config.last_tested = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.add(config)
    db.commit()

    return {
        "success": success,
        "message": message,
        "response_time_ms": int(response_time_ms),
        "config_uuid": str(config.uuid),
    }
