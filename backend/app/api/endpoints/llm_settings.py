"""
API endpoints for user LLM settings management
"""

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

router = APIRouter()
logger = logging.getLogger(__name__)


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
            description="OpenAI's GPT models - reliable and well-supported"
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.VLLM,
            default_model="gpt-oss",
            default_base_url="http://localhost:8012/v1",
            requires_api_key=False,
            supports_custom_url=True,
            max_context_length=32768,
            description="vLLM server for local or custom model deployment"
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.OLLAMA,
            default_model="llama2:7b-chat",
            default_base_url="http://localhost:11434/v1",
            requires_api_key=False,
            supports_custom_url=True,
            max_context_length=4096,
            description="Ollama for local model deployment"
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.CLAUDE,
            default_model="claude-3-haiku-20240307",
            default_base_url="https://api.anthropic.com/v1",
            requires_api_key=True,
            supports_custom_url=False,
            max_context_length=200000,
            description="Anthropic's Claude models - excellent for analysis"
        ),
        schemas.ProviderDefaults(
            provider=schemas.LLMProvider.OPENROUTER,
            default_model="anthropic/claude-3-haiku",
            default_base_url="https://openrouter.ai/api/v1",
            requires_api_key=True,
            supports_custom_url=False,
            max_context_length=200000,
            description="OpenRouter provides access to many model providers"
        )
    ]


@router.get("/providers", response_model=schemas.SupportedProvidersResponse)
def get_supported_providers() -> Any:
    """
    Get list of supported LLM providers with their default configurations
    """
    providers = _get_provider_defaults()
    return schemas.SupportedProvidersResponse(providers=providers)


@router.get("/status", response_model=schemas.LLMSettingsStatus)
def get_llm_settings_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get status information about user's LLM settings
    """
    user_settings = db.query(models.UserLLMSettings).filter(
        models.UserLLMSettings.user_id == current_user.id
    ).first()

    if not user_settings:
        return schemas.LLMSettingsStatus(
            has_settings=False,
            using_system_default=True
        )

    return schemas.LLMSettingsStatus(
        has_settings=True,
        provider=user_settings.provider,
        model_name=user_settings.model_name,
        test_status=user_settings.test_status,
        last_tested=user_settings.last_tested,
        is_active=user_settings.is_active,
        using_system_default=False
    )


@router.get("/", response_model=schemas.UserLLMSettingsPublic)
def get_user_llm_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user's LLM settings (without API key for security)
    """
    user_settings = db.query(models.UserLLMSettings).filter(
        models.UserLLMSettings.user_id == current_user.id
    ).first()

    if not user_settings:
        raise HTTPException(
            status_code=404,
            detail="User LLM settings not found. Create settings first."
        )

    # Convert to public schema (excludes API key)
    return schemas.UserLLMSettingsPublic(
        **user_settings.__dict__,
        has_api_key=bool(user_settings.api_key)
    )


@router.post("/", response_model=schemas.UserLLMSettingsPublic)
def create_user_llm_settings(
    *,
    db: Session = Depends(get_db),
    settings_in: schemas.UserLLMSettingsCreate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Create LLM settings for the current user
    """
    # Check if user already has settings
    existing_settings = db.query(models.UserLLMSettings).filter(
        models.UserLLMSettings.user_id == current_user.id
    ).first()

    if existing_settings:
        raise HTTPException(
            status_code=400,
            detail="User already has LLM settings. Use PUT to update."
        )

    # Test encryption before proceeding
    if not test_encryption():
        raise HTTPException(
            status_code=500,
            detail="Encryption system is not working properly"
        )

    # Encrypt API key if provided
    encrypted_api_key = None
    if settings_in.api_key:
        encrypted_api_key = encrypt_api_key(settings_in.api_key)
        if not encrypted_api_key:
            raise HTTPException(
                status_code=500,
                detail="Failed to encrypt API key"
            )

    # Create new settings
    settings_data = settings_in.model_dump(exclude={'api_key'})
    settings_data.update({
        "user_id": current_user.id,
        "api_key": encrypted_api_key
    })

    user_settings = models.UserLLMSettings(**settings_data)
    db.add(user_settings)
    db.commit()
    db.refresh(user_settings)

    return schemas.UserLLMSettingsPublic(
        **user_settings.__dict__,
        has_api_key=bool(user_settings.api_key)
    )


@router.put("/", response_model=schemas.UserLLMSettingsPublic)
def update_user_llm_settings(
    *,
    db: Session = Depends(get_db),
    settings_in: schemas.UserLLMSettingsUpdate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Update current user's LLM settings
    """
    user_settings = db.query(models.UserLLMSettings).filter(
        models.UserLLMSettings.user_id == current_user.id
    ).first()

    if not user_settings:
        raise HTTPException(
            status_code=404,
            detail="User LLM settings not found. Create settings first."
        )

    # Handle API key encryption
    update_data = settings_in.model_dump(exclude_unset=True, exclude={'api_key'})

    if 'api_key' in settings_in.model_fields_set and settings_in.api_key is not None:
        if settings_in.api_key.strip():  # Non-empty API key
            if not test_encryption():
                raise HTTPException(
                    status_code=500,
                    detail="Encryption system is not working properly"
                )

            encrypted_api_key = encrypt_api_key(settings_in.api_key)
            if not encrypted_api_key:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to encrypt API key"
                )
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
        setattr(user_settings, field, value)

    db.add(user_settings)
    db.commit()
    db.refresh(user_settings)

    return schemas.UserLLMSettingsPublic(
        **user_settings.__dict__,
        has_api_key=bool(user_settings.api_key)
    )


@router.delete("/")
def delete_user_llm_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Delete current user's LLM settings (revert to system defaults)
    """
    user_settings = db.query(models.UserLLMSettings).filter(
        models.UserLLMSettings.user_id == current_user.id
    ).first()

    if not user_settings:
        raise HTTPException(
            status_code=404,
            detail="User LLM settings not found"
        )

    db.delete(user_settings)
    db.commit()

    return {"detail": "LLM settings deleted successfully. Using system defaults."}


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
            timeout=test_request.timeout or 30
        )

        # Create and test LLM service
        llm_service = LLMService(config)
        try:
            success, message = await llm_service.validate_connection()
            response_time = int((time.time() - start_time) * 1000)

            return schemas.ConnectionTestResponse(
                success=success,
                status=schemas.ConnectionStatus.SUCCESS if success else schemas.ConnectionStatus.FAILED,
                message=message,
                response_time_ms=response_time
            )
        finally:
            await llm_service.close()

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"LLM connection test failed: {e}")

        return schemas.ConnectionTestResponse(
            success=False,
            status=schemas.ConnectionStatus.FAILED,
            message=f"Connection test failed: {str(e)}",
            response_time_ms=response_time
        )


@router.post("/test-current", response_model=schemas.ConnectionTestResponse)
async def test_current_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Test connection using current user's saved LLM settings
    """
    user_settings = db.query(models.UserLLMSettings).filter(
        models.UserLLMSettings.user_id == current_user.id
    ).first()

    if not user_settings:
        raise HTTPException(
            status_code=404,
            detail="User LLM settings not found. Create settings first."
        )

    # Decrypt API key
    api_key = None
    if user_settings.api_key:
        api_key = decrypt_api_key(user_settings.api_key)
        if not api_key and user_settings.api_key:  # Decryption failed
            raise HTTPException(
                status_code=500,
                detail="Failed to decrypt stored API key"
            )

    # Test connection
    test_request = schemas.ConnectionTestRequest(
        provider=schemas.LLMProvider(user_settings.provider),
        model_name=user_settings.model_name,
        api_key=api_key,
        base_url=user_settings.base_url,
        timeout=user_settings.timeout
    )

    result = await test_llm_connection(test_request=test_request, current_user=current_user)

    # Update test status in database
    user_settings.test_status = result.status.value
    user_settings.test_message = result.message
    user_settings.last_tested = db.execute("SELECT NOW()").scalar()

    db.add(user_settings)
    db.commit()

    return result


@router.get("/encryption-test")
def test_encryption_endpoint(
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Test the encryption system (for debugging)
    """
    if not test_encryption():
        raise HTTPException(
            status_code=500,
            detail="Encryption system is not working properly"
        )

    return {"status": "success", "message": "Encryption system is working correctly"}
