"""
Prompt management utilities for AI summarization
"""

import logging
from typing import Optional

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models import SummaryPrompt
from app.models import UserSetting

# Database-only prompt management - no fallbacks needed

logger = logging.getLogger(__name__)


def get_user_active_prompt(user_id: Optional[int] = None, db: Optional[Session] = None) -> str:
    """
    Get the active summary prompt for a user, falling back to system default

    Args:
        user_id: User ID to get prompt for (None for system default)
        db: Optional database session (creates new one if not provided)

    Returns:
        The prompt text to use for summarization
    """
    should_close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        # If no user specified, return system default
        if user_id is None:
            return get_system_default_prompt(db)

        # Get user's active prompt setting
        active_setting = db.query(UserSetting).filter(
            and_(
                UserSetting.user_id == user_id,
                UserSetting.setting_key == "active_summary_prompt_id"
            )
        ).first()

        active_prompt = None
        if active_setting and active_setting.setting_value:
            try:
                prompt_id = int(active_setting.setting_value)
                active_prompt = db.query(SummaryPrompt).filter(
                    and_(
                        SummaryPrompt.id == prompt_id,
                        SummaryPrompt.is_active
                    )
                ).first()
            except (ValueError, TypeError):
                logger.warning(f"Invalid prompt ID in user setting: {active_setting.setting_value}")

        # If no active prompt or prompt not found, get system default from database
        if not active_prompt:
            return get_system_default_prompt(db)

        # Verify user has access to this prompt
        if not active_prompt.is_system_default and active_prompt.user_id != user_id:
            logger.warning(f"User {user_id} attempted to use inaccessible prompt {active_prompt.id}")
            return get_system_default_prompt(db)

        return active_prompt.prompt_text

    except Exception as e:
        logger.error(f"Error getting user active prompt for user {user_id}: {e}")
        raise

    finally:
        if should_close_db:
            db.close()


def get_system_default_prompt(db: Session) -> str:
    """
    Get the system default prompt from database with intelligent fallback

    Args:
        db: Database session

    Returns:
        System default prompt text
    """
    try:
        # First try to find a universal/general prompt
        logger.info("Querying for universal/general system prompt")
        default_prompt = db.query(SummaryPrompt).filter(
            and_(
                SummaryPrompt.is_system_default,
                SummaryPrompt.content_type == "general",
                SummaryPrompt.is_active,
                or_(
                    SummaryPrompt.name.ilike("%universal%"),
                    SummaryPrompt.name.ilike("%general%")
                )
            )
        ).first()

        if default_prompt:
            logger.info(f"Found universal system prompt: {default_prompt.name}")
            return default_prompt.prompt_text

        # If no universal prompt found, fallback to any general system prompt
        logger.info("No universal prompt found, trying any general system prompt")
        default_prompt = db.query(SummaryPrompt).filter(
            and_(
                SummaryPrompt.is_system_default,
                SummaryPrompt.content_type == "general",
                SummaryPrompt.is_active
            )
        ).first()

        if default_prompt:
            logger.info(f"Found general system prompt: {default_prompt.name}")
            return default_prompt.prompt_text

        # Final fallback: any active system prompt
        logger.warning("No general system prompt found, using any available system prompt")
        any_system_prompt = db.query(SummaryPrompt).filter(
            and_(
                SummaryPrompt.is_system_default,
                SummaryPrompt.is_active
            )
        ).first()

        if any_system_prompt:
            logger.warning(f"Using fallback system prompt: {any_system_prompt.name} (type: {any_system_prompt.content_type})")
            return any_system_prompt.prompt_text
        else:
            logger.error("No active system default prompts found in database at all!")
            raise ValueError("No active system default prompt found in database")

    except Exception as e:
        logger.error(f"Error getting system default prompt: {e}")
        raise


def get_prompt_for_content_type(content_type: str, user_id: Optional[int] = None, db: Optional[Session] = None) -> str:
    """
    Get the best prompt for a specific content type

    Args:
        content_type: Type of content (meeting, interview, podcast, etc.)
        user_id: User ID to get prompt for (None for system default)
        db: Optional database session

    Returns:
        The most appropriate prompt text for the content type
    """
    should_close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        # First try to get user's active prompt
        if user_id:
            user_prompt = get_user_active_prompt(user_id, db)
            # If we got a user-specific prompt, use it
            if user_prompt:
                return user_prompt

        # Try to get system prompt specific to content type
        content_type_prompt = db.query(SummaryPrompt).filter(
            and_(
                SummaryPrompt.is_system_default,
                SummaryPrompt.content_type == content_type,
                SummaryPrompt.is_active
            )
        ).first()

        if content_type_prompt:
            return content_type_prompt.prompt_text

        # Fall back to general system default
        return get_system_default_prompt(db)

    except Exception as e:
        logger.error(f"Error getting prompt for content type {content_type}: {e}")
        raise

    finally:
        if should_close_db:
            db.close()


def create_user_prompt(
    user_id: int,
    name: str,
    prompt_text: str,
    description: Optional[str] = None,
    content_type: Optional[str] = None,
    db: Optional[Session] = None
) -> Optional[SummaryPrompt]:
    """
    Create a new custom prompt for a user

    Args:
        user_id: User ID
        name: Prompt name
        prompt_text: Prompt content
        description: Optional description
        content_type: Optional content type
        db: Optional database session

    Returns:
        Created prompt or None if failed
    """
    should_close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        # Check user's prompt count limit
        user_prompt_count = db.query(SummaryPrompt).filter(
            and_(
                SummaryPrompt.user_id == user_id,
                SummaryPrompt.is_active
            )
        ).count()

        if user_prompt_count >= 50:  # Same limit as in API
            logger.warning(f"User {user_id} has reached prompt limit")
            return None

        # Create new prompt
        prompt = SummaryPrompt(
            user_id=user_id,
            name=name,
            prompt_text=prompt_text,
            description=description,
            content_type=content_type,
            is_system_default=False,
            is_active=True
        )

        db.add(prompt)
        db.commit()
        db.refresh(prompt)

        return prompt

    except Exception as e:
        logger.error(f"Error creating user prompt: {e}")
        db.rollback()
        return None

    finally:
        if should_close_db:
            db.close()


def set_user_active_prompt(user_id: int, prompt_id: int, db: Optional[Session] = None) -> bool:
    """
    Set a user's active summary prompt

    Args:
        user_id: User ID
        prompt_id: Prompt ID to set as active
        db: Optional database session

    Returns:
        True if successful, False otherwise
    """
    should_close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        # Verify prompt exists and user has access
        prompt = db.query(SummaryPrompt).filter(SummaryPrompt.id == prompt_id).first()
        if not prompt or not prompt.is_active:
            return False

        # Check access
        if not prompt.is_system_default and prompt.user_id != user_id:
            return False

        # Update or create setting
        setting = db.query(UserSetting).filter(
            and_(
                UserSetting.user_id == user_id,
                UserSetting.setting_key == "active_summary_prompt_id"
            )
        ).first()

        if setting:
            setting.setting_value = str(prompt_id)
        else:
            setting = UserSetting(
                user_id=user_id,
                setting_key="active_summary_prompt_id",
                setting_value=str(prompt_id)
            )
            db.add(setting)

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Error setting user active prompt: {e}")
        db.rollback()
        return False

    finally:
        if should_close_db:
            db.close()
