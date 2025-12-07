"""
API endpoints for user LLM settings management
"""

import contextlib
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.services.llm_service import LLMConfig
from app.services.llm_service import LLMProvider as ServiceLLMProvider
from app.services.llm_service import LLMService
from app.utils.encryption import decrypt_api_key
from app.utils.encryption import encrypt_api_key
from app.utils.encryption import test_encryption
from app.utils.uuid_helpers import get_llm_config_by_uuid

router = APIRouter()
logger = logging.getLogger(__name__)


def _set_active_configuration(db: Session, user_id: int, config_id: int) -> None:
    """Helper function to set active LLM configuration for a user"""
    # Check if setting already exists
    existing_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == user_id,
            models.UserSetting.setting_key == "active_llm_config_id",
        )
        .first()
    )

    if existing_setting:
        existing_setting.setting_value = str(config_id)
        db.add(existing_setting)
    else:
        new_setting = models.UserSetting(
            user_id=user_id,
            setting_key="active_llm_config_id",
            setting_value=str(config_id),
        )
        db.add(new_setting)

    db.commit()


def _get_provider_defaults() -> list[schemas.ProviderDefaults]:
    """Get default configurations for all supported providers"""
    return [
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.OPENAI,
            default_model="gpt-4o-mini",
            default_base_url="https://api.openai.com/v1",
            requires_api_key=True,
            supports_custom_url=True,
            max_context_length=128000,
            description="OpenAI's GPT models - reliable and well-supported",
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.VLLM,
            default_model="gpt-oss",
            default_base_url="http://localhost:8012/v1",
            requires_api_key=False,
            supports_custom_url=True,
            max_context_length=32768,
            description="vLLM server for local or custom model deployment",
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.OLLAMA,
            default_model="llama2:7b-chat",
            default_base_url="http://localhost:11434/v1",
            requires_api_key=False,
            supports_custom_url=True,
            max_context_length=4096,
            description="Ollama for local model deployment",
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.CLAUDE,
            default_model="claude-3-haiku-20240307",
            default_base_url="https://api.anthropic.com/v1",
            requires_api_key=True,
            supports_custom_url=False,
            max_context_length=200000,
            description="Anthropic's Claude models - excellent for analysis",
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.OPENROUTER,
            default_model="anthropic/claude-3-haiku",
            default_base_url="https://openrouter.ai/api/v1",
            requires_api_key=True,
            supports_custom_url=False,
            max_context_length=200000,
            description="OpenRouter provides access to many model providers",
        ),
    ]


@router.get("/providers", response_model=schemas.SupportedProvidersResponse)
def get_supported_providers() -> Any:
    """
    Get list of supported LLM providers with their default configurations
    """
    providers = _get_provider_defaults()
    return schemas.SupportedProvidersResponse(providers=providers)


@router.get("/", response_model=schemas.UserLLMConfigurationsList)
def get_user_configurations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get all user's LLM configurations
    """
    # Get all user configurations
    configurations = (
        db.query(models.UserLLMSettings)
        .filter(models.UserLLMSettings.user_id == current_user.id)
        .order_by(models.UserLLMSettings.created_at.desc())
        .all()
    )

    # Get active configuration ID
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_llm_config_id",
        )
        .first()
    )

    active_config_uuid = None
    if active_setting and active_setting.setting_value:
        with contextlib.suppress(ValueError):
            active_config_id = int(active_setting.setting_value)
            # Convert integer ID to UUID by finding the config
            active_config = (
                db.query(models.UserLLMSettings)
                .filter(models.UserLLMSettings.id == active_config_id)
                .first()
            )
            if active_config:
                active_config_uuid = active_config.uuid

    # Convert to public schemas
    public_configs = []
    for config in configurations:
        # Let FastAPI handle the conversion automatically
        public_configs.append(config)

    return schemas.UserLLMConfigurationsList(
        configurations=public_configs,
        active_configuration_id=active_config_uuid,
        total=len(public_configs),
    )


@router.get("/status", response_model=schemas.LLMSettingsStatus)
def get_llm_settings_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get status information about user's LLM settings
    """
    # Get all configurations
    total_configs = (
        db.query(models.UserLLMSettings)
        .filter(models.UserLLMSettings.user_id == current_user.id)
        .count()
    )

    if total_configs == 0:
        return schemas.LLMSettingsStatus(
            has_settings=False, total_configurations=0, using_system_default=True
        )

    # Get active configuration
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_llm_config_id",
        )
        .first()
    )

    active_config = None
    if active_setting and active_setting.setting_value:
        try:
            active_config_id = int(active_setting.setting_value)
            active_config = (
                db.query(models.UserLLMSettings)
                .filter(
                    models.UserLLMSettings.user_id == current_user.id,
                    models.UserLLMSettings.id == active_config_id,
                )
                .first()
            )
        except ValueError:
            pass

    active_public = None
    if active_config:
        active_public = active_config

    return schemas.LLMSettingsStatus(
        has_settings=True,
        active_configuration=active_public,
        total_configurations=total_configs,
        using_system_default=not bool(active_config),
    )


@router.get("/config/{config_uuid}", response_model=schemas.UserLLMSettingsPublic)
def get_user_configuration(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific user's LLM configuration
    """
    user_config = get_llm_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    # Convert to public schema (excludes API key)
    return user_config


@router.post("/", response_model=schemas.UserLLMSettingsPublic)
def create_user_llm_configuration(
    *,
    db: Session = Depends(get_db),
    settings_in: schemas.UserLLMSettingsCreate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Create a new LLM configuration for the current user
    """
    # Check if user already has a configuration with this name
    existing_config = (
        db.query(models.UserLLMSettings)
        .filter(
            models.UserLLMSettings.user_id == current_user.id,
            models.UserLLMSettings.name == settings_in.name,
        )
        .first()
    )

    if existing_config:
        raise HTTPException(
            status_code=400,
            detail=f"Configuration with name '{settings_in.name}' already exists.",
        )

    # Test encryption before proceeding
    if not test_encryption():
        raise HTTPException(status_code=500, detail="Encryption system is not working properly")

    # Encrypt API key if provided
    encrypted_api_key = None
    if settings_in.api_key:
        encrypted_api_key = encrypt_api_key(settings_in.api_key)
        if not encrypted_api_key:
            raise HTTPException(status_code=500, detail="Failed to encrypt API key")

    # Create new configuration
    settings_data = settings_in.model_dump(exclude={"api_key"})
    settings_data.update({"user_id": current_user.id, "api_key": encrypted_api_key})

    user_config = models.UserLLMSettings(**settings_data)
    db.add(user_config)
    db.commit()
    db.refresh(user_config)

    # If this is the user's first configuration, make it active
    existing_count = (
        db.query(models.UserLLMSettings)
        .filter(models.UserLLMSettings.user_id == current_user.id)
        .count()
    )

    if existing_count == 1:  # This is the first config
        _set_active_configuration(db, current_user.id, user_config.id)

    return user_config


@router.put("/config/{config_uuid}", response_model=schemas.UserLLMSettingsPublic)
def update_user_llm_configuration(
    config_uuid: str,
    *,
    db: Session = Depends(get_db),
    settings_in: schemas.UserLLMSettingsUpdate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Update a specific LLM configuration
    """
    user_config = get_llm_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    config_id = user_config.id

    # Check for name conflicts if name is being updated
    if settings_in.name and settings_in.name != user_config.name:
        existing_config = (
            db.query(models.UserLLMSettings)
            .filter(
                models.UserLLMSettings.user_id == current_user.id,
                models.UserLLMSettings.name == settings_in.name,
                models.UserLLMSettings.id != config_id,
            )
            .first()
        )

        if existing_config:
            raise HTTPException(
                status_code=400,
                detail=f"Configuration with name '{settings_in.name}' already exists.",
            )

    # Handle API key encryption
    update_data = settings_in.model_dump(exclude_unset=True, exclude={"api_key"})

    if "api_key" in settings_in.model_fields_set and settings_in.api_key is not None:
        if settings_in.api_key.strip():  # Non-empty API key
            if not test_encryption():
                raise HTTPException(
                    status_code=500, detail="Encryption system is not working properly"
                )

            encrypted_api_key = encrypt_api_key(settings_in.api_key)
            if not encrypted_api_key:
                raise HTTPException(status_code=500, detail="Failed to encrypt API key")
            update_data["api_key"] = encrypted_api_key
        else:  # Empty API key means remove it
            update_data["api_key"] = None

    # Reset test status when settings change
    if update_data:
        update_data["test_status"] = "untested"
        update_data["test_message"] = None
        update_data["last_tested"] = None

    # Apply updates
    for field, value in update_data.items():
        setattr(user_config, field, value)

    db.add(user_config)
    db.commit()
    db.refresh(user_config)

    return user_config


@router.post("/set-active", response_model=schemas.UserLLMSettingsPublic)
def set_active_configuration(
    *,
    db: Session = Depends(get_db),
    request: schemas.SetActiveConfigRequest,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Set the active LLM configuration for the user
    """
    # Verify the configuration exists and belongs to the user using UUID
    user_config = get_llm_config_by_uuid(db, request.configuration_id)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    # Set as active using the integer ID (internal)
    _set_active_configuration(db, current_user.id, user_config.id)

    return user_config


@router.delete("/config/{config_uuid}")
def delete_user_llm_configuration(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Delete a specific LLM configuration
    """
    user_config = get_llm_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    config_id = user_config.id

    # Check if this is the active configuration
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_llm_config_id",
        )
        .first()
    )

    is_active = False
    if active_setting and active_setting.setting_value == str(config_id):
        is_active = True

    # Delete the configuration
    db.delete(user_config)

    # If this was the active configuration, clear the active setting
    # or set another configuration as active if available
    if is_active:
        # Find another configuration to set as active
        remaining_config = (
            db.query(models.UserLLMSettings)
            .filter(
                models.UserLLMSettings.user_id == current_user.id,
                models.UserLLMSettings.id != config_id,
            )
            .first()
        )

        if remaining_config:
            # Set the first remaining config as active
            _set_active_configuration(db, current_user.id, remaining_config.id)
        else:
            # No configurations left, remove the active setting
            if active_setting:
                db.delete(active_setting)

    db.commit()

    return {"detail": "Configuration deleted successfully."}


@router.delete("/all")
def delete_all_user_configurations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Delete all user's LLM configurations (revert to system defaults)
    """
    # Delete all configurations
    deleted_count = (
        db.query(models.UserLLMSettings)
        .filter(models.UserLLMSettings.user_id == current_user.id)
        .delete()
    )

    # Delete active setting
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_llm_config_id",
        )
        .first()
    )

    if active_setting:
        db.delete(active_setting)

    db.commit()

    return {
        "detail": f"All {deleted_count} configurations deleted successfully. Using system defaults."
    }


@router.post("/test", response_model=schemas.ConnectionTestResponse)
async def test_llm_connection(
    *,
    test_request: schemas.ConnectionTestRequest,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Test connection to LLM provider without saving settings
    """
    start_time = time.time()

    try:
        # Map schema enum to service enum
        service_provider = ServiceLLMProvider(test_request.provider.value)

        # Create LLM config for testing
        config = LLMConfig(
            provider=service_provider,
            model=test_request.model_name,
            api_key=test_request.api_key,
            base_url=test_request.base_url,
        )

        # Create and test LLM service
        llm_service = LLMService(config)
        try:
            # Test the connection
            actual_url = llm_service.endpoints[service_provider]
            logger.debug(
                f"Testing LLM connection to: {actual_url} (Provider: {service_provider}, Model: {test_request.model_name})"
            )

            success, message = llm_service.validate_connection()
            response_time = int((time.time() - start_time) * 1000)

            return schemas.ConnectionTestResponse(
                success=success,
                status=schemas.ConnectionStatus.SUCCESS
                if success
                else schemas.ConnectionStatus.FAILED,
                message=f"{message} (URL: {actual_url})",
                response_time_ms=response_time,
            )
        finally:
            llm_service.close()

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"LLM connection test failed: {e}")

        return schemas.ConnectionTestResponse(
            success=False,
            status=schemas.ConnectionStatus.FAILED,
            message=f"Connection test failed: {str(e)}",
            response_time_ms=response_time,
        )


@router.post("/test-current", response_model=schemas.ConnectionTestResponse)
async def test_active_configuration(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Test connection using current user's active LLM configuration
    """
    # Get active configuration
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            models.UserSetting.user_id == current_user.id,
            models.UserSetting.setting_key == "active_llm_config_id",
        )
        .first()
    )

    if not active_setting or not active_setting.setting_value:
        raise HTTPException(
            status_code=404,
            detail="No active LLM configuration found. Please set an active configuration first.",
        )

    try:
        active_config_id = int(active_setting.setting_value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid active configuration ID") from e

    user_config = (
        db.query(models.UserLLMSettings)
        .filter(
            models.UserLLMSettings.user_id == current_user.id,
            models.UserLLMSettings.id == active_config_id,
        )
        .first()
    )

    if not user_config:
        raise HTTPException(
            status_code=404,
            detail="Active LLM configuration not found.",
        )

    # Decrypt API key
    api_key = None
    if user_config.api_key:
        api_key = decrypt_api_key(user_config.api_key)
        if not api_key and user_config.api_key:  # Decryption failed
            raise HTTPException(status_code=500, detail="Failed to decrypt stored API key")

    # Test connection
    test_request = schemas.ConnectionTestRequest(
        provider=schemas.LLMProvider(user_config.provider),
        model_name=user_config.model_name,
        api_key=api_key,
        base_url=user_config.base_url,
    )

    result = await test_llm_connection(test_request=test_request, current_user=current_user)

    # Update test status in database
    from sqlalchemy import text

    user_config.test_status = result.status.value
    user_config.test_message = result.message
    user_config.last_tested = db.execute(text("SELECT NOW()")).scalar()

    db.add(user_config)
    db.commit()

    return result


@router.post("/test-config/{config_uuid}", response_model=schemas.ConnectionTestResponse)
async def test_specific_configuration(
    config_uuid: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Test connection for a specific LLM configuration
    """
    user_config = get_llm_config_by_uuid(db, config_uuid)

    if user_config.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this configuration",
        )

    # Decrypt API key
    api_key = None
    if user_config.api_key:
        api_key = decrypt_api_key(user_config.api_key)
        if not api_key and user_config.api_key:  # Decryption failed
            raise HTTPException(status_code=500, detail="Failed to decrypt stored API key")

    # Test connection
    test_request = schemas.ConnectionTestRequest(
        provider=schemas.LLMProvider(user_config.provider),
        model_name=user_config.model_name,
        api_key=api_key,
        base_url=user_config.base_url,
    )

    result = await test_llm_connection(test_request=test_request, current_user=current_user)

    # Update test status in database
    from sqlalchemy import text

    user_config.test_status = result.status.value
    user_config.test_message = result.message
    user_config.last_tested = db.execute(text("SELECT NOW()")).scalar()

    db.add(user_config)
    db.commit()

    return result


@router.get("/ollama/models")
async def get_ollama_models(
    base_url: str,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get available models from an Ollama instance
    """
    import aiohttp

    try:
        # Clean up base URL
        clean_url = base_url.strip().rstrip("/")
        if clean_url.endswith("/v1"):
            clean_url = clean_url[:-3]  # Remove /v1 suffix

        models_url = f"{clean_url}/api/tags"

        timeout = aiohttp.ClientTimeout(total=10)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(models_url) as response,
        ):
            if response.status == 200:
                data = await response.json()
                models = []

                if "models" in data:
                    for model in data["models"]:
                        models.append(
                            {
                                "name": model.get("name", ""),
                                "size": model.get("size", 0),
                                "modified_at": model.get("modified_at", ""),
                                "digest": model.get("digest", ""),
                                "details": model.get("details", {}),
                                "display_name": model.get("name", "").split(":")[
                                    0
                                ],  # Remove tag for display
                            }
                        )

                return {
                    "success": True,
                    "models": models,
                    "total": len(models),
                    "message": f"Found {len(models)} models on Ollama server",
                }
            else:
                error_text = await response.text()
                return {
                    "success": False,
                    "models": [],
                    "total": 0,
                    "message": f"Failed to fetch models: HTTP {response.status} - {error_text}",
                }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "models": [],
            "total": 0,
            "message": f"Connection error: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error fetching Ollama models from {base_url}: {e}")
        return {
            "success": False,
            "models": [],
            "total": 0,
            "message": f"Unexpected error: {str(e)}",
        }


@router.get("/openai-compatible/models")
async def get_openai_compatible_models(
    base_url: str,
    api_key: str | None = None,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get available models from an OpenAI-compatible API endpoint
    Supports: OpenAI, vLLM, OpenRouter, and other OpenAI-compatible providers
    """
    import aiohttp

    try:
        # Clean up base URL
        clean_url = base_url.strip().rstrip("/")
        if not clean_url.endswith("/v1"):
            clean_url = f"{clean_url}/v1"

        models_url = f"{clean_url}/models"

        # Prepare headers
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        timeout = aiohttp.ClientTimeout(total=10)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(models_url, headers=headers) as response,
        ):
            if response.status == 200:
                data = await response.json()
                models = []

                if "data" in data:
                    for model in data["data"]:
                        models.append(
                            {
                                "name": model.get("id", ""),
                                "id": model.get("id", ""),
                                "owned_by": model.get("owned_by", ""),
                                "created": model.get("created", 0),
                            }
                        )

                return {
                    "success": True,
                    "models": models,
                    "total": len(models),
                    "message": f"Found {len(models)} models",
                }
            else:
                error_text = await response.text()
                return {
                    "success": False,
                    "models": [],
                    "total": 0,
                    "message": f"Failed to fetch models: HTTP {response.status} - {error_text}",
                }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "models": [],
            "total": 0,
            "message": f"Connection error: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Error fetching OpenAI-compatible models from {base_url}: {e}")
        return {
            "success": False,
            "models": [],
            "total": 0,
            "message": f"Unexpected error: {str(e)}",
        }


@router.get("/encryption-test")
def test_encryption_endpoint(
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Test the encryption system (for debugging)
    """
    if not test_encryption():
        raise HTTPException(status_code=500, detail="Encryption system is not working properly")

    return {"status": "success", "message": "Encryption system is working correctly"}
