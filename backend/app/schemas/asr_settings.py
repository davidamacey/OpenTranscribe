"""Pydantic schemas for ASR provider settings."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel
from pydantic import field_validator


class ASRProvider(str, Enum):
    LOCAL = "local"
    DEEPGRAM = "deepgram"
    ASSEMBLYAI = "assemblyai"
    OPENAI = "openai"
    GOOGLE = "google"
    AZURE = "azure"
    AWS = "aws"
    SPEECHMATICS = "speechmatics"
    GLADIA = "gladia"


class ASRModelInfo(BaseModel):
    id: str
    display_name: str
    description: str
    price_per_min_batch: float | None = None
    price_per_min_stream: float | None = None
    languages: int | None = None
    is_default: bool = False
    is_medical: bool = False
    supports_diarization: bool = False
    supports_vocabulary: bool = False
    supports_translation: bool = False
    supports_confidence: bool = False
    max_file_size_mb: int | None = None


class ASRProviderInfo(BaseModel):
    id: str
    display_name: str
    requires_api_key: bool
    requires_region: bool = False
    supports_custom_url: bool = False
    supports_diarization: bool
    supports_vocabulary: bool
    supports_translation: bool
    description: str = ""
    models: list[ASRModelInfo]


class ASRProviderCatalog(BaseModel):
    providers: list[ASRProviderInfo]


class UserASRSettingsBase(BaseModel):
    name: str
    provider: ASRProvider
    model_name: str
    base_url: str | None = None
    region: str | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        if len(v) > 100:
            raise ValueError("Name must be 100 characters or less")
        return v


class UserASRSettingsCreate(UserASRSettingsBase):
    api_key: str | None = None


class UserASRSettingsUpdate(BaseModel):
    name: str | None = None
    provider: ASRProvider | None = None
    model_name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    region: str | None = None
    is_active: bool | None = None


class UserASRSettingsResponse(UserASRSettingsBase):
    id: int
    uuid: UUID
    user_id: int
    has_api_key: bool
    last_tested: datetime | None = None
    test_status: str | None = None
    test_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ASRSettingsList(BaseModel):
    configs: list[UserASRSettingsResponse]
    active_config_id: int | None = None
    active_config_uuid: UUID | None = None


class ASRConnectionTestRequest(BaseModel):
    provider: ASRProvider
    api_key: str | None = None
    base_url: str | None = None
    region: str | None = None
    model_name: str | None = None


class ASRConnectionTestResult(BaseModel):
    success: bool
    message: str
    # response_time_ms is the canonical field name used internally
    response_time_ms: float | None = None

    # latency_ms is an alias for API consumers that expect the spec name
    @property
    def latency_ms(self) -> float | None:
        return self.response_time_ms


class SetActiveASRConfigRequest(BaseModel):
    # Both fields are optional so callers can send either name.
    # At least one must be provided; endpoint validation enforces this.
    config_uuid: UUID | None = None  # canonical field name
    uuid: UUID | None = None  # spec-compatibility alias

    def resolved_uuid(self) -> UUID | None:
        """Return whichever of config_uuid / uuid was provided, preferring config_uuid."""
        return self.config_uuid or self.uuid


class ASRStatusResponse(BaseModel):
    has_settings: bool
    active_config: UserASRSettingsResponse | None = None
    using_local_default: bool
    deployment_mode: str
    asr_configured: bool
    # Convenience fields so callers don't have to unpack active_config
    active_provider: str | None = None
    active_model: str | None = None
    active_config_uuid: UUID | None = None
    is_cloud_provider: bool = False
