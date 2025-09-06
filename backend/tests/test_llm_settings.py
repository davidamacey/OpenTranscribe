"""
Tests for LLM settings functionality
"""

from unittest.mock import Mock
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.main import app
from app.utils.encryption import decrypt_api_key
from app.utils.encryption import encrypt_api_key
from app.utils.encryption import test_encryption


class TestEncryption:
    """Test encryption utilities"""

    def test_encryption_basic_functionality(self):
        """Test basic encryption/decryption"""
        test_key = "sk-test123456789abcdef"

        # Encrypt
        encrypted = encrypt_api_key(test_key)
        assert encrypted is not None
        assert encrypted != test_key

        # Decrypt
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == test_key

    def test_encryption_empty_key(self):
        """Test encryption with empty/None keys"""
        assert encrypt_api_key(None) is None
        assert encrypt_api_key("") is None
        assert encrypt_api_key("   ") is None

        assert decrypt_api_key(None) is None
        assert decrypt_api_key("") is None
        assert decrypt_api_key("   ") is None

    def test_encryption_system_test(self):
        """Test encryption system validation"""
        assert test_encryption() is True


@pytest.fixture
def mock_db():
    """Mock database session"""
    return Mock(spec=Session)


@pytest.fixture
def mock_user():
    """Mock user object"""
    user = Mock()
    user.id = 1
    user.email = "test@example.com"
    user.full_name = "Test User"
    return user


@pytest.fixture
def client():
    """Test client"""
    return TestClient(app)


class TestLLMSettingsModel:
    """Test UserLLMSettings model"""

    def test_user_llm_settings_creation(self, mock_db):
        """Test creating UserLLMSettings instance"""
        settings = models.UserLLMSettings(
            user_id=1,
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="encrypted_key",
            base_url="https://api.openai.com/v1",
            max_tokens=2000,
            temperature="0.3",
            timeout=60,
            is_active=True,
            test_status="untested"
        )

        assert settings.user_id == 1
        assert settings.provider == "openai"
        assert settings.model_name == "gpt-4o-mini"
        assert settings.is_active is True


class TestLLMSettingsAPI:
    """Test LLM settings API endpoints"""

    @patch('app.api.endpoints.llm_settings.get_current_active_user')
    @patch('app.api.endpoints.llm_settings.get_db')
    def test_get_providers(self, mock_get_db, mock_get_user, client):
        """Test getting supported providers"""
        mock_get_user.return_value = Mock(id=1)

        response = client.get("/api/llm-settings/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert len(data["providers"]) > 0

        # Check provider structure
        provider = data["providers"][0]
        assert "provider" in provider
        assert "default_model" in provider
        assert "requires_api_key" in provider
        assert "supports_custom_url" in provider
        assert "description" in provider

    @patch('app.api.endpoints.llm_settings.get_current_active_user')
    @patch('app.api.endpoints.llm_settings.get_db')
    def test_get_status_no_settings(self, mock_get_db, mock_get_user, client):
        """Test getting status when user has no settings"""
        mock_get_user.return_value = Mock(id=1)
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = mock_db

        response = client.get("/api/llm-settings/status")

        assert response.status_code == 200
        data = response.json()
        assert data["has_settings"] is False
        assert data["using_system_default"] is True

    @patch('app.api.endpoints.llm_settings.get_current_active_user')
    @patch('app.api.endpoints.llm_settings.get_db')
    def test_get_settings_not_found(self, mock_get_db, mock_get_user, client):
        """Test getting settings when none exist"""
        mock_get_user.return_value = Mock(id=1)
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = mock_db

        response = client.get("/api/llm-settings")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch('app.api.endpoints.llm_settings.get_current_active_user')
    @patch('app.api.endpoints.llm_settings.get_db')
    @patch('app.utils.encryption.test_encryption')
    @patch('app.utils.encryption.encrypt_api_key')
    def test_create_settings(self, mock_encrypt, mock_test_encryption, mock_get_db, mock_get_user, client):
        """Test creating new LLM settings"""
        mock_get_user.return_value = Mock(id=1)
        mock_test_encryption.return_value = True
        mock_encrypt.return_value = "encrypted_key"

        # Mock database interactions
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing settings
        mock_get_db.return_value = mock_db

        # Mock created settings
        created_settings = Mock()
        created_settings.id = 1
        created_settings.user_id = 1
        created_settings.provider = "openai"
        created_settings.model_name = "gpt-4o-mini"
        created_settings.api_key = "encrypted_key"
        created_settings.has_api_key = True
        created_settings.__dict__ = {
            "id": 1,
            "user_id": 1,
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "max_tokens": 2000,
            "temperature": "0.3",
            "timeout": 60,
            "is_active": True,
            "last_tested": None,
            "test_status": None,
            "test_message": None,
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-01-01T00:00:00"
        }

        mock_db.refresh.return_value = None
        mock_db.add.return_value = None
        mock_db.commit.return_value = None

        # Mock the models.UserLLMSettings constructor
        with patch('app.api.endpoints.llm_settings.models.UserLLMSettings', return_value=created_settings):
            settings_data = {
                "provider": "openai",
                "model_name": "gpt-4o-mini",
                "api_key": "sk-test123456789",
                "base_url": "https://api.openai.com/v1",
                "max_tokens": 2000,
                "temperature": "0.3",
                "timeout": 60,
                "is_active": True
            }

            response = client.post("/api/llm-settings", json=settings_data)

            assert response.status_code == 200
            data = response.json()
            assert data["provider"] == "openai"
            assert data["model_name"] == "gpt-4o-mini"

    @patch('app.api.endpoints.llm_settings.get_current_active_user')
    @patch('app.api.endpoints.llm_settings.get_db')
    def test_create_settings_already_exist(self, mock_get_db, mock_get_user, client):
        """Test creating settings when they already exist"""
        mock_get_user.return_value = Mock(id=1)

        # Mock existing settings
        existing_settings = Mock()
        existing_settings.id = 1
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_settings
        mock_get_db.return_value = mock_db

        settings_data = {
            "provider": "openai",
            "model_name": "gpt-4o-mini"
        }

        response = client.post("/api/llm-settings", json=settings_data)

        assert response.status_code == 400
        assert "already has" in response.json()["detail"]

    @patch('app.api.endpoints.llm_settings.get_current_active_user')
    def test_test_connection_invalid_provider(self, mock_get_user, client):
        """Test connection with invalid provider"""
        mock_get_user.return_value = Mock(id=1)

        test_data = {
            "provider": "invalid_provider",
            "model_name": "test-model"
        }

        response = client.post("/api/llm-settings/test", json=test_data)

        # Should handle invalid provider gracefully
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "failed" in data["status"].lower()


class TestLLMSettingsSchemas:
    """Test LLM settings Pydantic schemas"""

    def test_llm_settings_create_validation(self):
        """Test creation schema validation"""
        # Valid data
        valid_data = {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "max_tokens": 2000,
            "temperature": "0.3",
            "timeout": 60
        }

        settings = schemas.UserLLMSettingsCreate(**valid_data)
        assert settings.provider == "openai"
        assert settings.max_tokens == 2000

    def test_llm_settings_validation_errors(self):
        """Test schema validation errors"""
        # Invalid max_tokens
        with pytest.raises(ValueError, match="max_tokens must be between"):
            schemas.UserLLMSettingsCreate(
                provider="openai",
                model_name="gpt-4",
                max_tokens=0  # Too low
            )

        # Invalid temperature
        with pytest.raises(ValueError, match="temperature must be between"):
            schemas.UserLLMSettingsCreate(
                provider="openai",
                model_name="gpt-4",
                temperature="3.0"  # Too high
            )

        # Invalid timeout
        with pytest.raises(ValueError, match="timeout must be between"):
            schemas.UserLLMSettingsCreate(
                provider="openai",
                model_name="gpt-4",
                timeout=1  # Too low
            )

    def test_connection_test_request(self):
        """Test connection test request schema"""
        request = schemas.ConnectionTestRequest(
            provider="vllm",
            model_name="llama2:7b",
            base_url="http://localhost:8012/v1",
            timeout=30
        )

        assert request.provider == "vllm"
        assert request.timeout == 30

    def test_provider_defaults(self):
        """Test provider defaults schema"""
        defaults = schemas.ProviderDefaults(
            provider="openai",
            default_model="gpt-4o-mini",
            default_base_url="https://api.openai.com/v1",
            requires_api_key=True,
            supports_custom_url=True,
            max_context_length=128000,
            description="OpenAI's GPT models"
        )

        assert defaults.provider == "openai"
        assert defaults.requires_api_key is True
        assert defaults.max_context_length == 128000


@pytest.mark.asyncio
class TestLLMServiceIntegration:
    """Test LLM service integration with user settings"""

    async def test_create_from_user_settings_not_found(self):
        """Test creating LLM service when user settings don't exist"""
        with patch('app.services.llm_service.SessionLocal') as mock_session_local:
            mock_db = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session_local.return_value = mock_db

            from app.services.llm_service import LLMService

            service = LLMService.create_from_user_settings(user_id=999)
            assert service is None

    async def test_create_from_user_settings_success(self):
        """Test creating LLM service from valid user settings"""
        with patch('app.services.llm_service.SessionLocal') as mock_session_local:
            with patch('app.utils.encryption.decrypt_api_key') as mock_decrypt:
                # Mock database
                mock_settings = Mock()
                mock_settings.provider = "openai"
                mock_settings.model_name = "gpt-4o-mini"
                mock_settings.api_key = "encrypted_key"
                mock_settings.base_url = "https://api.openai.com/v1"
                mock_settings.max_tokens = 2000
                mock_settings.temperature = "0.3"
                mock_settings.timeout = 60
                mock_settings.is_active = True

                mock_db = Mock()
                mock_db.query.return_value.filter.return_value.first.return_value = mock_settings
                mock_session_local.return_value = mock_db

                # Mock decryption
                mock_decrypt.return_value = "sk-test123456789"

                from app.services.llm_service import LLMService

                service = LLMService.create_from_user_settings(user_id=1)

                assert service is not None
                assert service.config.provider.value == "openai"
                assert service.config.model == "gpt-4o-mini"

    async def test_create_from_settings_with_fallback(self):
        """Test creating LLM service with fallback to system defaults"""
        with patch('app.services.llm_service.LLMService.create_from_user_settings') as mock_user_settings:
            with patch('app.services.llm_service.LLMService.create_from_system_settings') as mock_system_settings:
                # Mock user settings failure
                mock_user_settings.return_value = None
                mock_system_settings.return_value = Mock()

                from app.services.llm_service import LLMService

                service = LLMService.create_from_settings(user_id=1)

                mock_user_settings.assert_called_once_with(1)
                mock_system_settings.assert_called_once()


class TestLLMSettingsIntegration:
    """Integration tests for LLM settings"""

    def test_encryption_integration(self):
        """Test that encryption works end-to-end"""
        # Test with various API key formats
        test_keys = [
            "sk-1234567890abcdef",
            "api_key_123",
            "Bearer token123",
            "very-long-api-key-with-special-chars!@#$%^&*()"
        ]

        for key in test_keys:
            encrypted = encrypt_api_key(key)
            assert encrypted is not None
            assert encrypted != key

            decrypted = decrypt_api_key(encrypted)
            assert decrypted == key

    @patch('app.services.llm_service.SessionLocal')
    def test_user_llm_service_creation_flow(self, mock_session_local):
        """Test complete flow of creating LLM service from user settings"""
        from app.services.llm_service import LLMService

        # Mock successful user settings retrieval
        mock_settings = Mock()
        mock_settings.provider = "openai"
        mock_settings.model_name = "gpt-4o-mini"
        mock_settings.api_key = encrypt_api_key("sk-test123")
        mock_settings.base_url = None
        mock_settings.max_tokens = 4000
        mock_settings.temperature = "0.5"
        mock_settings.timeout = 120
        mock_settings.is_active = True

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_settings
        mock_session_local.return_value = mock_db

        # Test service creation
        service = LLMService.create_from_user_settings(user_id=1)

        assert service is not None
        assert service.config.provider.value == "openai"
        assert service.config.model == "gpt-4o-mini"
        assert service.config.max_tokens == 4000
        assert float(service.config.temperature) == 0.5
        assert service.config.timeout == 120


if __name__ == "__main__":
    pytest.main([__file__])
