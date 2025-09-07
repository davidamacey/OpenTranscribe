"""
API endpoints for AI summarization prompt management
"""

import contextlib
from typing import Any
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.api.endpoints.auth import get_current_active_user
from app.db.base import get_db

router = APIRouter()


@router.get("/", response_model=schemas.SummaryPromptList)
def get_prompts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    include_system: bool = Query(True, description="Include system prompts"),
    include_user: bool = Query(True, description="Include user's custom prompts"),
) -> Any:
    """
    Retrieve summary prompts with filtering and pagination.

    This endpoint allows users to fetch both system-provided prompts and their own
    custom prompts for AI summarization. Results can be filtered by content type
    and paginated for efficient retrieval.

    Args:
        db: Database session dependency
        current_user: Current authenticated user
        skip: Number of prompts to skip for pagination (default: 0)
        limit: Maximum number of prompts to return (default: 100, max: 1000)
        content_type: Optional filter by content type ('meeting', 'interview',
                     'podcast', 'documentary', 'general')
        include_system: Whether to include system-provided default prompts
        include_user: Whether to include user's custom prompts

    Returns:
        SummaryPromptList: Paginated list of prompts with metadata

    Raises:
        HTTPException: If database query fails
    """
    # Build filter conditions
    conditions = []

    if content_type:
        conditions.append(models.SummaryPrompt.content_type == content_type)

    # Filter by ownership
    ownership_conditions = []
    if include_system:
        ownership_conditions.append(models.SummaryPrompt.is_system_default)
    if include_user:
        ownership_conditions.append(
            and_(
                models.SummaryPrompt.user_id == current_user.id,
                ~models.SummaryPrompt.is_system_default,
            )
        )

    if ownership_conditions:
        conditions.append(or_(*ownership_conditions))

    # Only active prompts
    conditions.append(models.SummaryPrompt.is_active)

    # Get prompts
    query = db.query(models.SummaryPrompt)
    if conditions:
        query = query.filter(and_(*conditions))

    total = query.count()
    prompts = (
        query.order_by(
            models.SummaryPrompt.is_system_default.desc(),  # System prompts first
            models.SummaryPrompt.name,
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return schemas.SummaryPromptList(
        prompts=prompts,
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        size=len(prompts),
        has_next=(skip + limit) < total,
        has_prev=skip > 0,
    )


@router.get(
    "/by-content-type/{content_type}", response_model=schemas.ContentTypePromptsResponse
)
def get_prompts_by_content_type(
    content_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get prompts organized by content type with active prompt indication.

    This endpoint provides a structured view of prompts for a specific content type,
    separating system prompts from user-created prompts, and indicating which
    prompt is currently active for the user.

    Args:
        content_type: The content type to filter by ('meeting', 'interview', etc.)
        db: Database session dependency
        current_user: Current authenticated user

    Returns:
        ContentTypePromptsResponse: Organized prompts with active prompt ID

    Raises:
        HTTPException: If content_type is invalid or database query fails
    """
    # Validate content type
    valid_types = {"meeting", "interview", "podcast", "documentary", "general"}
    if content_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type. Must be one of: {valid_types}",
        )

    # Get system prompts for this content type
    system_prompts = (
        db.query(models.SummaryPrompt)
        .filter(
            and_(
                models.SummaryPrompt.content_type == content_type,
                models.SummaryPrompt.is_system_default,
                models.SummaryPrompt.is_active,
            )
        )
        .order_by(models.SummaryPrompt.name)
        .all()
    )

    # Get user's custom prompts for this content type
    user_prompts = (
        db.query(models.SummaryPrompt)
        .filter(
            and_(
                models.SummaryPrompt.content_type == content_type,
                models.SummaryPrompt.user_id == current_user.id,
                not models.SummaryPrompt.is_system_default,
                models.SummaryPrompt.is_active,
            )
        )
        .order_by(models.SummaryPrompt.name)
        .all()
    )

    # Get active prompt ID for this user
    active_prompt_setting = (
        db.query(models.UserSetting)
        .filter(
            and_(
                models.UserSetting.user_id == current_user.id,
                models.UserSetting.setting_key == "active_summary_prompt_id",
            )
        )
        .first()
    )

    active_prompt_id = None
    if active_prompt_setting and active_prompt_setting.setting_value:
        with contextlib.suppress(ValueError, TypeError):
            active_prompt_id = int(active_prompt_setting.setting_value)

    return schemas.ContentTypePromptsResponse(
        content_type=content_type,
        system_prompts=system_prompts,
        user_prompts=user_prompts,
        active_prompt_id=active_prompt_id,
    )


@router.post("/", response_model=schemas.SummaryPrompt)
def create_prompt(
    *,
    db: Session = Depends(get_db),
    prompt_in: schemas.SummaryPromptCreate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Create a new custom summary prompt for the current user.

    Allows users to create personalized prompts for AI summarization. Each user
    is limited to a maximum of 50 custom prompts to prevent abuse.

    Args:
        db: Database session dependency
        prompt_in: The prompt data to create (name, description, prompt_text, etc.)
        current_user: Current authenticated user

    Returns:
        SummaryPrompt: The created prompt object

    Raises:
        HTTPException: If user has reached the prompt limit (50) or creation fails
    """
    # Check if user already has too many prompts
    user_prompt_count = (
        db.query(models.SummaryPrompt)
        .filter(
            and_(
                models.SummaryPrompt.user_id == current_user.id,
                models.SummaryPrompt.is_active,
            )
        )
        .count()
    )

    if user_prompt_count >= 50:  # Reasonable limit
        raise HTTPException(
            status_code=400, detail="Maximum number of custom prompts reached (50)"
        )

    prompt_data = prompt_in.dict()
    prompt_data.update({"user_id": current_user.id, "is_system_default": False})

    prompt = models.SummaryPrompt(**prompt_data)
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


@router.get("/{prompt_id}", response_model=schemas.SummaryPrompt)
def get_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific prompt by ID
    """
    prompt = (
        db.query(models.SummaryPrompt)
        .filter(models.SummaryPrompt.id == prompt_id)
        .first()
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Check access: system prompts are public, user prompts are private
    if not prompt.is_system_default and prompt.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return prompt


@router.put("/{prompt_id}", response_model=schemas.SummaryPrompt)
def update_prompt(
    *,
    db: Session = Depends(get_db),
    prompt_id: int,
    prompt_in: schemas.SummaryPromptUpdate,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Update a custom summary prompt (user's own prompts only)
    """
    prompt = (
        db.query(models.SummaryPrompt)
        .filter(models.SummaryPrompt.id == prompt_id)
        .first()
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Only allow users to update their own custom prompts
    if prompt.is_system_default or prompt.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify system prompts or other users' prompts",
        )

    update_data = prompt_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prompt, field, value)

    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


@router.delete("/{prompt_id}")
def delete_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Delete a custom summary prompt (user's own prompts only)
    """
    prompt = (
        db.query(models.SummaryPrompt)
        .filter(models.SummaryPrompt.id == prompt_id)
        .first()
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Only allow users to delete their own custom prompts
    if prompt.is_system_default or prompt.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete system prompts or other users' prompts",
        )

    # Check if this is the user's active prompt
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            and_(
                models.UserSetting.user_id == current_user.id,
                models.UserSetting.setting_key == "active_summary_prompt_id",
                models.UserSetting.setting_value == str(prompt_id),
            )
        )
        .first()
    )

    if active_setting:
        # Reset to default prompt
        db.delete(active_setting)

    db.delete(prompt)
    db.commit()
    return {"detail": "Prompt deleted successfully"}


@router.get("/active/current", response_model=schemas.ActivePromptResponse)
def get_active_prompt(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Get the user's currently active summary prompt
    """
    # Get user's active prompt setting
    active_setting = (
        db.query(models.UserSetting)
        .filter(
            and_(
                models.UserSetting.user_id == current_user.id,
                models.UserSetting.setting_key == "active_summary_prompt_id",
            )
        )
        .first()
    )

    active_prompt = None
    active_prompt_id = None

    if active_setting and active_setting.setting_value:
        try:
            active_prompt_id = int(active_setting.setting_value)
            active_prompt = (
                db.query(models.SummaryPrompt)
                .filter(models.SummaryPrompt.id == active_prompt_id)
                .first()
            )
        except (ValueError, TypeError):
            pass

    # If no active prompt or prompt not found, get default system prompt
    if not active_prompt:
        # First try to find a universal/general prompt
        active_prompt = (
            db.query(models.SummaryPrompt)
            .filter(
                and_(
                    models.SummaryPrompt.is_system_default,
                    models.SummaryPrompt.content_type == "general",
                    models.SummaryPrompt.is_active,
                    or_(
                        models.SummaryPrompt.name.ilike("%universal%"),
                        models.SummaryPrompt.name.ilike("%general%"),
                    ),
                )
            )
            .first()
        )

        # If no universal prompt found, fallback to any general system prompt
        if not active_prompt:
            active_prompt = (
                db.query(models.SummaryPrompt)
                .filter(
                    and_(
                        models.SummaryPrompt.is_system_default,
                        models.SummaryPrompt.content_type == "general",
                        models.SummaryPrompt.is_active,
                    )
                )
                .first()
            )

        # Final fallback: any active system prompt
        if not active_prompt:
            active_prompt = (
                db.query(models.SummaryPrompt)
                .filter(
                    and_(
                        models.SummaryPrompt.is_system_default,
                        models.SummaryPrompt.is_active,
                    )
                )
                .first()
            )

        active_prompt_id = active_prompt.id if active_prompt else None

    return schemas.ActivePromptResponse(
        active_prompt_id=active_prompt_id, active_prompt=active_prompt
    )


@router.post("/active/set", response_model=schemas.ActivePromptResponse)
def set_active_prompt(
    *,
    db: Session = Depends(get_db),
    prompt_selection: schemas.ActivePromptSelection,
    current_user: models.User = Depends(get_current_active_user),
) -> Any:
    """
    Set the user's active summary prompt
    """
    # Verify prompt exists and user has access
    prompt = (
        db.query(models.SummaryPrompt)
        .filter(models.SummaryPrompt.id == prompt_selection.prompt_id)
        .first()
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Check access: system prompts are public, user prompts are private
    if not prompt.is_system_default and prompt.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Cannot use other users' custom prompts"
        )

    if not prompt.is_active:
        raise HTTPException(status_code=400, detail="Cannot use inactive prompt")

    # Update or create user setting
    setting = (
        db.query(models.UserSetting)
        .filter(
            and_(
                models.UserSetting.user_id == current_user.id,
                models.UserSetting.setting_key == "active_summary_prompt_id",
            )
        )
        .first()
    )

    if setting:
        setting.setting_value = str(prompt_selection.prompt_id)
    else:
        setting = models.UserSetting(
            user_id=current_user.id,
            setting_key="active_summary_prompt_id",
            setting_value=str(prompt_selection.prompt_id),
        )
        db.add(setting)

    db.commit()
    db.refresh(prompt)

    return schemas.ActivePromptResponse(
        active_prompt_id=prompt.id, active_prompt=prompt
    )
