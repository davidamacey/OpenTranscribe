"""
API endpoints for user ASR settings management
"""

import contextlib
import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.utils.encryption import decrypt_api_key
from app.utils.encryption import encrypt_api_key
from app.utils.encryption import test_encryption
from app.utils.uuid_helpers import get_asr_config_by_uuid

router = APIRouter()
logger = logging.getLogger(__name__)


def _set_active_asr_configuration(db: Session, user_id: int, config_id: int) -> None:
    """Helper function to set active ASR configuration for a user."""
    existing_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )

    if existing_setting:
        existing_setting.setting_value = str(config_id)  # type: ignore[assignment]
        db.add(existing_setting)
    else:
        new_setting = models.UserSetting(
            user_id=user_id,
            setting_key="active_asr_config_id",
            setting_value=str(config_id),
        )
        db.add(new_setting)

    db.commit()


def _get_provider_defaults() -> list[schemas.ASRProviderDefaults]:
    """Get default configurations for all supported ASR providers."""
    return [
        schemas.ASRProviderDefaults(
            provider=schemas.ASRProvider.DEEPGRAM,
            default_model="nova-3-medical",
            requires_api_key=True,
            description="Deepgram Nova-3 Medical — cloud ASR with built-in diarization and medical vocabulary",
        ),
        schemas.ASRProviderDefaults(
            provider=schemas.ASRProvider.WHISPERX,
            default_model="large-v2",
            requires_api_key=False,
            description="WhisperX — local GPU-based transcription with PyAnnote diarization (requires GPU)",
        ),
    ]


@router.get("/providers", response_model=schemas.SupportedASRProvidersResponse)
def get_supported_providers() -> Any:
    """Get list of supported ASR providers with their default configurations."""
    providers = _get_provider_defaults()
    return schemas.SupportedASRProvidersResponse(providers=providers)


@router.get("", response_model=schemas.UserASRConfigurationsList)
def get_user_configurations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Get all user's ASR configurations."""
    configurations = (
        db.query(models.UserASRSettings)
        .filter(models.UserASRSettings.user_id == current_user.id)
        .order_by(models.UserASRSettings.created_at.desc())
        .all()
    )

    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )

    active_config_uuid: UUID | None = None
    if active_setting and active_setting.setting_value:
        with contextlib.suppress(ValueError):
            active_config_id = int(active_setting.setting_value)
            active_config = (
                db.query(models.UserASRSettings)
                .filter(models.UserASRSettings.id == active_config_id)
                .first()
            )
            if active_config:
                active_config_uuid = UUID(str(active_config.uuid))

    public_configs: list[schemas.UserASRSettingsPublic] = []
    for config in configurations:
        public_configs.append(config)  # type: ignore[arg-type]

    return schemas.UserASRConfigurationsList(
        configurations=public_configs,
        active_configuration_id=active_config_uuid,
        total=len(public_configs),
    )


@router.get("/status", response_model=schemas.ASRSettingsStatus)
def get_asr_settings_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Get status information about user's ASR settings."""
    total_configs = (
        db.query(models.UserASRSettings)
        .filter(models.UserASRSettings.user_id == current_user.id)
        .count()
    )

    if total_configs == 0:
        return schemas.ASRSettingsStatus(
            has_settings=False, total_configurations=0, using_env_default=True
        )

    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )

    active_config = None
    if active_setting and active_setting.setting_value:
        try:
            active_config_id = int(active_setting.setting_value)
            active_config = (
                db.query(models.UserASRSettings)
                .filter(
                    models.UserASRSettings.user_id == current_user.id,
                    models.UserASRSettings.id == active_config_id,
                )
                .first()
            )
        except ValueError:
            pass

    return schemas.ASRSettingsStatus(
        has_settings=True,
        active_configuration=active_config,
        total_configurations=total_configs,
        using_env_default=not bool(active_config),
    )


@router.get("/config/{config_uuid}", response_model=schemas.UserASRSettingsPublic)
def get_user_configuration(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Get a specific user's ASR configuration."""
    user_config = get_asr_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    return user_config


@router.get("/config/{config_uuid}/api-key")
def get_config_api_key(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Get the decrypted API key for a specific configuration (for edit mode)."""
    user_config = get_asr_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    decrypted_key = None
    if user_config.api_key:
        decrypted_key = decrypt_api_key(str(user_config.api_key))

    return {"api_key": decrypted_key}


@router.post("", response_model=schemas.UserASRSettingsPublic)
def create_user_asr_configuration(
    *,
    db: Session = Depends(get_db),
    settings_in: schemas.UserASRSettingsCreate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Create a new ASR configuration for the current user."""
    existing_config = (
        db.query(models.UserASRSettings)
        .filter(
            models.UserASRSettings.user_id == current_user.id,
            models.UserASRSettings.name == settings_in.name,
        )
        .first()
    )

    if existing_config:
        raise HTTPException(
            status_code=400,
            detail=f"Configuration with name '{settings_in.name}' already exists.",
        )

    if not test_encryption():
        raise HTTPException(status_code=500, detail="Encryption system is not working properly")

    encrypted_api_key = None
    if settings_in.api_key:
        encrypted_api_key = encrypt_api_key(settings_in.api_key)
        if not encrypted_api_key:
            raise HTTPException(status_code=500, detail="Failed to encrypt API key")

    settings_data = settings_in.model_dump(exclude={"api_key"})
    settings_data.update({"user_id": current_user.id, "api_key": encrypted_api_key})

    user_config = models.UserASRSettings(**settings_data)
    db.add(user_config)
    db.commit()
    db.refresh(user_config)

    # If this is the user's first configuration, make it active
    existing_count = (
        db.query(models.UserASRSettings)
        .filter(models.UserASRSettings.user_id == current_user.id)
        .count()
    )

    if existing_count == 1:
        _set_active_asr_configuration(db, int(current_user.id), int(user_config.id))

    return user_config


@router.put("/config/{config_uuid}", response_model=schemas.UserASRSettingsPublic)
def update_user_asr_configuration(
    config_uuid: str,
    *,
    db: Session = Depends(get_db),
    settings_in: schemas.UserASRSettingsUpdate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Update a specific ASR configuration."""
    user_config = get_asr_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    config_id = user_config.id

    if settings_in.name and settings_in.name != user_config.name:
        existing_config = (
            db.query(models.UserASRSettings)
            .filter(
                models.UserASRSettings.user_id == current_user.id,
                models.UserASRSettings.name == settings_in.name,
                models.UserASRSettings.id != config_id,
            )
            .first()
        )

        if existing_config:
            raise HTTPException(
                status_code=400,
                detail=f"Configuration with name '{settings_in.name}' already exists.",
            )

    update_data = settings_in.model_dump(exclude_unset=True, exclude={"api_key"})

    if "api_key" in settings_in.model_fields_set and settings_in.api_key is not None:
        if settings_in.api_key.strip():
            if not test_encryption():
                raise HTTPException(
                    status_code=500, detail="Encryption system is not working properly"
                )

            encrypted_api_key = encrypt_api_key(settings_in.api_key)
            if not encrypted_api_key:
                raise HTTPException(status_code=500, detail="Failed to encrypt API key")
            update_data["api_key"] = encrypted_api_key
        else:
            update_data["api_key"] = None

    if update_data:
        update_data["test_status"] = "untested"
        update_data["test_message"] = None
        update_data["last_tested"] = None

    for field, value in update_data.items():
        setattr(user_config, field, value)

    db.add(user_config)
    db.commit()
    db.refresh(user_config)

    return user_config


@router.post("/set-active", response_model=schemas.UserASRSettingsPublic)
def set_active_configuration(
    *,
    db: Session = Depends(get_db),
    request: schemas.SetActiveASRConfigRequest,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Set the active ASR configuration for the user."""
    user_config = get_asr_config_by_uuid(db, request.configuration_id)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    _set_active_asr_configuration(db, int(current_user.id), int(user_config.id))

    return user_config


@router.delete("/config/{config_uuid}")
def delete_user_asr_configuration(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Delete a specific ASR configuration."""
    user_config = get_asr_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    config_id = user_config.id

    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_asr_config_id",
        )
        .first()
    )

    is_active = False
    if active_setting and active_setting.setting_value == str(config_id):
        is_active = True

    db.delete(user_config)

    if is_active:
        remaining_config = (
            db.query(models.UserASRSettings)
            .filter(
                models.UserASRSettings.user_id == current_user.id,
                models.UserASRSettings.id != config_id,
            )
            .first()
        )

        if remaining_config:
            _set_active_asr_configuration(db, int(current_user.id), int(remaining_config.id))
        else:
            if active_setting:
                db.delete(active_setting)

    db.commit()

    return {"detail": "Configuration deleted successfully."}


@router.post("/test", response_model=schemas.ASRConnectionTestResponse)
async def test_asr_connection(
    *,
    test_request: schemas.ASRConnectionTestRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Test connection to ASR provider without saving settings."""
    start_time = time.time()

    try:
        effective_api_key = test_request.api_key
        if not effective_api_key and test_request.config_id:
            try:
                config = (
                    db.query(models.UserASRSettings)
                    .filter(
                        models.UserASRSettings.uuid == test_request.config_id,
                        models.UserASRSettings.user_id == current_user.id,
                    )
                    .first()
                )
                if config and config.api_key:
                    effective_api_key = decrypt_api_key(str(config.api_key))
            except Exception as e:
                logger.warning(
                    f"Could not retrieve stored API key for config {test_request.config_id}: {e}"
                )

        if test_request.provider == schemas.ASRProvider.DEEPGRAM:
            result = await _test_deepgram_connection(effective_api_key, test_request.model_name)
        elif test_request.provider == schemas.ASRProvider.WHISPERX:
            result = _test_whisperx_availability()
        else:
            result = (False, f"Unknown provider: {test_request.provider}")

        response_time = int((time.time() - start_time) * 1000)
        success, message = result

        return schemas.ASRConnectionTestResponse(
            success=success,
            status=schemas.asr_settings.ConnectionStatus.SUCCESS
            if success
            else schemas.asr_settings.ConnectionStatus.FAILED,
            message=message,
            response_time_ms=response_time,
        )

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"ASR connection test failed: {e}")

        return schemas.ASRConnectionTestResponse(
            success=False,
            status=schemas.asr_settings.ConnectionStatus.FAILED,
            message=f"Connection test failed: {e!s}",
            response_time_ms=response_time,
        )


@router.post("/test-config/{config_uuid}", response_model=schemas.ASRConnectionTestResponse)
async def test_stored_configuration(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """Test connection using a stored ASR configuration."""
    user_config = get_asr_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    start_time = time.time()

    try:
        api_key = None
        if user_config.api_key:
            api_key = decrypt_api_key(str(user_config.api_key))

        if user_config.provider == "deepgram":
            success, message = await _test_deepgram_connection(api_key, user_config.model_name)
        elif user_config.provider == "whisperx":
            success, message = _test_whisperx_availability()
        else:
            success, message = False, f"Unknown provider: {user_config.provider}"

        response_time = int((time.time() - start_time) * 1000)

        # Update test status on the config
        status = "success" if success else "failed"
        user_config.test_status = status  # type: ignore[assignment]
        user_config.test_message = message  # type: ignore[assignment]
        from datetime import datetime, timezone

        user_config.last_tested = datetime.now(timezone.utc)  # type: ignore[assignment]
        db.add(user_config)
        db.commit()

        return schemas.ASRConnectionTestResponse(
            success=success,
            status=schemas.asr_settings.ConnectionStatus.SUCCESS
            if success
            else schemas.asr_settings.ConnectionStatus.FAILED,
            message=message,
            response_time_ms=response_time,
        )

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"ASR config test failed: {e}")

        return schemas.ASRConnectionTestResponse(
            success=False,
            status=schemas.asr_settings.ConnectionStatus.FAILED,
            message=f"Connection test failed: {e!s}",
            response_time_ms=response_time,
        )


async def _test_deepgram_connection(api_key: str | None, model_name: str) -> tuple[bool, str]:
    """Test Deepgram API connection by making a lightweight API call."""
    if not api_key:
        return False, "No API key provided"

    try:
        from deepgram import DeepgramClient

        client = DeepgramClient(api_key)
        # Use the projects endpoint as a lightweight connectivity check
        response = client.manage.v("1").get_projects()
        project_count = len(response.projects) if hasattr(response, "projects") else 0
        return True, f"Connected to Deepgram successfully. Found {project_count} project(s). Model: {model_name}"
    except ImportError:
        return False, "deepgram-sdk package is not installed"
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            return False, "Invalid API key — authentication failed"
        if "403" in error_msg or "Forbidden" in error_msg:
            return False, "API key does not have sufficient permissions"
        return False, f"Deepgram connection failed: {error_msg}"


def _test_whisperx_availability() -> tuple[bool, str]:
    """Check if WhisperX is available (requires GPU)."""
    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            return True, f"GPU available: {gpu_name}. WhisperX can run."
        return False, "No GPU detected. WhisperX requires a CUDA-capable GPU."
    except ImportError:
        return False, "PyTorch is not installed. WhisperX requires PyTorch with CUDA support."
