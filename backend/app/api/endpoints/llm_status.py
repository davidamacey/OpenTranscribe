"""
LLM Status API endpoints
"""

import logging
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.llm_service import is_llm_available

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def get_llm_status(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Check if LLM services are available for the current user

    Returns:
        Dictionary containing LLM availability status and details
    """
    try:
        # Check if LLM is available for this user
        is_available = await is_llm_available(user_id=current_user.id)

        status_info = {"available": is_available, "user_id": current_user.id}

        if is_available:
            # Get additional info about the configured LLM
            try:
                llm_service = LLMService.create_from_settings(user_id=current_user.id)
                if llm_service:
                    status_info.update(
                        {
                            "provider": llm_service.config.provider.value,
                            "model": llm_service.config.model,
                            "message": "LLM service is available and configured",
                        }
                    )
                    await llm_service.close()
                else:
                    status_info.update(
                        {
                            "provider": None,
                            "model": None,
                            "message": "LLM service is not configured",
                        }
                    )
            except Exception as e:
                logger.warning(f"Error getting LLM service details: {e}")
                status_info.update(
                    {
                        "provider": "unknown",
                        "model": "unknown",
                        "message": f"LLM service error: {str(e)}",
                    }
                )
        else:
            status_info.update(
                {
                    "provider": None,
                    "model": None,
                    "message": "LLM service is not available. Please configure an LLM provider in your settings or check your server configuration.",
                }
            )

        return status_info

    except Exception as e:
        logger.error(f"Error checking LLM status: {e}")
        return {
            "available": False,
            "user_id": current_user.id,
            "provider": None,
            "model": None,
            "message": f"Error checking LLM status: {str(e)}",
        }


@router.get("/llm/providers")
async def get_available_providers(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Get list of supported LLM providers

    Returns:
        Dictionary containing supported providers and their info
    """
    try:
        providers = LLMService.get_supported_providers()

        return {
            "providers": providers,
            "total": len(providers),
            "message": "List of supported LLM providers",
        }

    except Exception as e:
        logger.error(f"Error getting LLM providers: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting LLM providers: {str(e)}") from e


@router.post("/llm/test-connection")
async def test_llm_connection(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """
    Test connection to the configured LLM service

    Returns:
        Dictionary containing connection test results
    """
    try:
        llm_service = LLMService.create_from_settings(user_id=current_user.id)
        if llm_service is None:
            return {
                "success": False,
                "message": "No LLM service configured",
                "details": "Please configure an LLM provider in your settings",
            }

        # Test the connection
        success, message = await llm_service.validate_connection()

        await llm_service.close()

        return {
            "success": success,
            "message": message,
            "provider": llm_service.config.provider.value,
            "model": llm_service.config.model,
        }

    except Exception as e:
        logger.error(f"Error testing LLM connection: {e}")
        return {
            "success": False,
            "message": f"Connection test failed: {str(e)}",
            "provider": "unknown",
            "model": "unknown",
        }
