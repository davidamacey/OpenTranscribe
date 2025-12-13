"""
Base Pydantic schemas for hybrid ID system.

Provides automatic UUID mapping for all response schemas.
Internal database uses integer IDs, external API uses UUIDs.
"""

import builtins
import contextlib
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import model_validator


class UUIDBaseSchema(BaseModel):
    """
    Base schema for models with UUID public identifiers.

    All response schemas should inherit from this to get automatic
    UUID mapping from internal integer IDs to external UUIDs.

    The SQLAlchemy model must have both:
    - id: Integer (internal primary key)
    - uuid: UUID (public identifier)

    The schema exposes 'id' as UUID to external API.
    """

    id: UUID  # Public UUID identifier (mapped from model.uuid)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def _convert_to_dict(cls, data: Any) -> dict[str, Any]:
        """Convert SQLAlchemy model to dict."""
        if isinstance(data.__dict__, dict):
            return {k: v for k, v in data.__dict__.items() if not k.startswith("_")}

        data_dict = {}
        for attr in dir(data):
            if not attr.startswith("_"):
                with contextlib.suppress(builtins.BaseException):
                    data_dict[attr] = getattr(data, attr)
        return data_dict

    @classmethod
    def _map_foreign_key_uuids(cls, data: Any, data_dict: dict[str, Any]) -> None:
        """Map foreign key UUIDs from related objects to the data dict."""
        # Map user relationship
        if hasattr(data, "user") and hasattr(data.user, "uuid"):
            data_dict["user_id"] = data.user.uuid

        # Map media_file relationship
        if hasattr(data, "media_file") and hasattr(data.media_file, "uuid"):
            data_dict["media_file_id"] = data.media_file.uuid

        # Map speaker relationship
        if hasattr(data, "speaker") and hasattr(data.speaker, "uuid"):
            data_dict["speaker_id"] = data.speaker.uuid

        # Map profile relationship
        if hasattr(data, "profile") and hasattr(data.profile, "uuid"):
            data_dict["profile_id"] = data.profile.uuid

    @model_validator(mode="before")
    @classmethod
    def map_uuid_to_id(cls, data: Any) -> Any:
        """
        Map the model's uuid field to id for the schema.
        Also maps foreign key UUIDs (user_id, media_file_id, etc.) from related models.

        This runs before Pydantic validation, allowing us to transform
        the SQLAlchemy model's data structure.
        """
        # Handle SQLAlchemy models
        if hasattr(data, "uuid") and hasattr(data, "__dict__"):
            data_dict = cls._convert_to_dict(data)

            # Map uuid to id
            if "uuid" in data_dict:
                data_dict["id"] = data_dict["uuid"]

            # Include computed properties that aren't in __dict__
            # has_api_key is a property on UserLLMSettings model
            if hasattr(data, "has_api_key") and "has_api_key" not in data_dict:
                data_dict["has_api_key"] = data.has_api_key

            # Map foreign key UUIDs from related objects
            cls._map_foreign_key_uuids(data, data_dict)

            return data_dict

        # Handle dicts
        if isinstance(data, dict) and "uuid" in data:
            data["id"] = data["uuid"]

        return data
