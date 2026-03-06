"""Pydantic schemas for custom vocabulary management."""
from datetime import datetime

from pydantic import BaseModel
from pydantic import field_validator

VALID_DOMAINS = ("medical", "legal", "corporate", "government", "technical", "general")


class CustomVocabularyBase(BaseModel):
    term: str
    domain: str = "general"
    category: str | None = None
    is_active: bool = True

    @field_validator("term")
    @classmethod
    def validate_term(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Term cannot be empty")
        if len(v) > 200:
            raise ValueError("Term must be 200 characters or less")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if v not in VALID_DOMAINS:
            raise ValueError(f"Domain must be one of: {', '.join(VALID_DOMAINS)}")
        return v


class CustomVocabularyCreate(CustomVocabularyBase):
    pass


class CustomVocabularyUpdate(BaseModel):
    term: str | None = None
    domain: str | None = None
    category: str | None = None
    is_active: bool | None = None


class CustomVocabularyResponse(CustomVocabularyBase):
    id: int
    user_id: int | None = None
    is_system: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CustomVocabularyBulkImport(BaseModel):
    terms: list[CustomVocabularyCreate]
