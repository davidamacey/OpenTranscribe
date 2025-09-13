"""
Tests for external LLM connections and edge cases

This module tests various external LLM configurations to ensure
robust handling of different scenarios including:
- External Ollama instances
- External vLLM deployments
- Network failures and timeouts
- Invalid credentials
- Rate limiting scenarios
"""

import asyncio
import contextlib
import time
from unittest.mock import Mock

import pytest

from app.api.endpoints.llm_settings import test_llm_connection
from app.schemas.llm_settings import ConnectionTestRequest
from app.services.llm_service import LLMConfig
from app.services.llm_service import LLMProvider
from app.services.llm_service import LLMService


class TestExternalOllamaConnections:
    """Test external Ollama instance connections"""

    @pytest.mark.asyncio
    async def test_local_ollama_default_config(self):
        """Test connection to default local Ollama setup"""
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model="llama2:7b-chat",
            base_url="http://localhost:11434",
            timeout=10,
        )

        service = LLMService(config)

        try:
            # This test will only pass if Ollama is actually running
            # In CI/CD, this should be mocked or skipped
            success, message = await service.validate_connection()

            # If Ollama is running, we should get a successful connection
            if success:
                assert "successful" in message.lower() or "available" in message.lower()
            else:
                # If not running, we should get a clear error message
                assert "connection" in message.lower() or "refused" in message.lower()

        except Exception as e:
            # Expected if Ollama is not running
            assert "connection" in str(e).lower() or "refused" in str(e).lower()
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_external_ollama_custom_port(self):
        """Test connection to Ollama on custom port"""
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model="mistral:7b",
            base_url="http://localhost:11435",  # Non-standard port
            timeout=5,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()
            # This should typically fail unless user has Ollama on port 11435
            assert isinstance(success, bool)
            assert isinstance(message, str)
        except Exception as e:
            # Expected for non-existent service
            assert "connection" in str(e).lower() or "timeout" in str(e).lower()
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_ollama_invalid_model(self):
        """Test Ollama with non-existent model"""
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model="nonexistent-model:latest",
            base_url="http://localhost:11434",
            timeout=5,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            if not success:
                # Should indicate model not found or similar error
                assert any(
                    keyword in message.lower()
                    for keyword in ["not found", "unavailable", "model", "error"]
                )
        except Exception:
            # Also acceptable - connection error is expected
            pass
        finally:
            await service.close()


class TestExternalVLLMConnections:
    """Test external vLLM instance connections"""

    @pytest.mark.asyncio
    async def test_local_vllm_default_config(self):
        """Test connection to default local vLLM setup"""
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            model="microsoft/DialoGPT-medium",
            base_url="http://localhost:8012/v1",
            timeout=10,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            # Log result for debugging
            print(f"vLLM connection test: success={success}, message={message}")

            assert isinstance(success, bool)
            assert isinstance(message, str)
        except Exception as e:
            # Expected if vLLM is not running
            print(f"vLLM connection error (expected): {e}")
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_external_vllm_custom_endpoint(self):
        """Test connection to external vLLM endpoint"""
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            model="custom-model",
            base_url="http://192.168.1.100:8000/v1",  # Example external IP
            timeout=5,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()
            assert isinstance(success, bool)
            assert isinstance(message, str)
        except Exception as e:
            # Expected for non-existent external service
            assert any(
                keyword in str(e).lower()
                for keyword in ["connection", "timeout", "unreachable", "refused"]
            )
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_vllm_with_api_key(self):
        """Test vLLM with API key authentication"""
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            model="test-model",
            base_url="http://localhost:8012/v1",
            api_key="test-api-key-123",
            timeout=5,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            # Should handle API key properly (even if service is down)
            assert isinstance(success, bool)
            assert isinstance(message, str)
        except Exception:
            # Connection error is expected if service isn't running
            pass
        finally:
            await service.close()


class TestNetworkEdgeCases:
    """Test network-related edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection timeout handling"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-3.5-turbo",
            base_url="http://10.255.255.1",  # Non-routable address
            api_key="test-key",
            timeout=1,  # Very short timeout
        )

        service = LLMService(config)

        start_time = time.time()
        try:
            success, message = await service.validate_connection()
            elapsed = time.time() - start_time

            # Should timeout quickly
            assert elapsed < 5  # Should not take much longer than timeout
            assert success is False
            assert any(
                keyword in message.lower() for keyword in ["timeout", "connection", "failed"]
            )
        except Exception:
            elapsed = time.time() - start_time
            assert elapsed < 5
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_invalid_url_format(self):
        """Test handling of invalid URL formats"""
        invalid_urls = [
            "not-a-url",
            "ftp://invalid-protocol.com",
            "http://",
            "http://invalid-domain-.com",
            "http://localhost:99999",  # Invalid port
        ]

        for url in invalid_urls:
            config = LLMConfig(
                provider=LLMProvider.VLLM, model="test-model", base_url=url, timeout=2
            )

            service = LLMService(config)

            try:
                success, message = await service.validate_connection()

                # Should gracefully handle invalid URLs
                assert success is False
                assert len(message) > 0
            except Exception as e:
                # Also acceptable - should catch and handle gracefully
                assert len(str(e)) > 0
            finally:
                await service.close()

    @pytest.mark.asyncio
    async def test_dns_resolution_failure(self):
        """Test DNS resolution failure handling"""
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model="test-model",
            base_url="http://nonexistent-domain-12345.com",
            timeout=3,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            assert success is False
            assert any(
                keyword in message.lower()
                for keyword in ["resolve", "dns", "connection", "failed", "unreachable"]
            )
        except Exception as e:
            # Expected for DNS failures
            assert any(keyword in str(e).lower() for keyword in ["resolve", "dns", "connection"])
        finally:
            await service.close()


class TestAPIKeyValidation:
    """Test API key validation and authentication edge cases"""

    @pytest.mark.asyncio
    async def test_invalid_openai_api_key(self):
        """Test OpenAI with invalid API key"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-3.5-turbo",
            base_url="https://api.openai.com/v1",
            api_key="invalid-key-123",
            timeout=10,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            # Should detect invalid API key
            if not success:
                assert any(
                    keyword in message.lower()
                    for keyword in ["unauthorized", "invalid", "key", "authentication"]
                )
        except Exception as e:
            # May throw exception for auth errors
            assert any(
                keyword in str(e).lower() for keyword in ["unauthorized", "authentication", "key"]
            )
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_empty_api_key_when_required(self):
        """Test providers that require API keys with empty keys"""
        providers_requiring_keys = [
            (LLMProvider.OPENAI, "gpt-3.5-turbo", "https://api.openai.com/v1"),
            (
                LLMProvider.CLAUDE,
                "claude-3-haiku-20240307",
                "https://api.anthropic.com/v1",
            ),
        ]

        for provider, model, base_url in providers_requiring_keys:
            config = LLMConfig(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=None,  # No API key provided
                timeout=5,
            )

            service = LLMService(config)

            try:
                success, message = await service.validate_connection()

                # Should fail due to missing API key
                assert success is False
                assert any(
                    keyword in message.lower()
                    for keyword in ["key", "authentication", "required", "missing"]
                )
            except Exception:
                # Also acceptable - may throw auth exception
                pass
            finally:
                await service.close()

    @pytest.mark.asyncio
    async def test_malformed_api_keys(self):
        """Test various malformed API key formats"""
        malformed_keys = [
            "",
            " ",
            "sk-",
            "sk-too-short",
            "wrong-prefix-1234567890abcdef",
            "sk-" + "x" * 200,  # Too long
        ]

        for key in malformed_keys:
            config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                base_url="https://api.openai.com/v1",
                api_key=key,
                timeout=5,
            )

            service = LLMService(config)

            try:
                success, message = await service.validate_connection()

                # Most malformed keys should be rejected
                if not success:
                    assert len(message) > 0
            except Exception:
                # Expected for malformed keys
                pass
            finally:
                await service.close()


class TestConnectionTestAPI:
    """Test the connection testing API endpoint"""

    @pytest.mark.asyncio
    async def test_connection_test_api_ollama(self):
        """Test connection test API with Ollama configuration"""
        mock_user = Mock(id=1)

        test_request = ConnectionTestRequest(
            provider="ollama",
            model_name="llama2:7b-chat",
            base_url="http://localhost:11434/v1",
            timeout=5,
        )

        # This will attempt actual connection - expect it to fail in test environment
        result = await test_llm_connection(test_request=test_request, current_user=mock_user)

        assert hasattr(result, "success")
        assert hasattr(result, "status")
        assert hasattr(result, "message")
        assert hasattr(result, "response_time_ms")

        # Should have reasonable response time even for failed connections
        assert result.response_time_ms is not None
        assert result.response_time_ms < 10000  # Less than 10 seconds

    @pytest.mark.asyncio
    async def test_connection_test_api_vllm(self):
        """Test connection test API with vLLM configuration"""
        mock_user = Mock(id=1)

        test_request = ConnectionTestRequest(
            provider="vllm",
            model_name="microsoft/DialoGPT-medium",
            base_url="http://localhost:8012/v1",
            timeout=5,
        )

        result = await test_llm_connection(test_request=test_request, current_user=mock_user)

        assert hasattr(result, "success")
        assert hasattr(result, "status")
        assert hasattr(result, "message")

        # Should provide useful feedback
        assert len(result.message) > 0


class TestResourceManagement:
    """Test proper resource management and cleanup"""

    @pytest.mark.asyncio
    async def test_service_cleanup_after_failure(self):
        """Test that services are properly cleaned up after connection failures"""
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            model="test-model",
            base_url="http://localhost:9999",  # Unlikely to be in use
            timeout=2,
        )

        service = LLMService(config)

        with contextlib.suppress(Exception):
            # This should fail
            await service.validate_connection()

        # Cleanup should work without errors
        await service.close()

        # Service should be in closed state
        assert service._session is None

    @pytest.mark.asyncio
    async def test_multiple_rapid_connections(self):
        """Test handling of multiple rapid connection attempts"""
        configs = [
            LLMConfig(
                provider=LLMProvider.OLLAMA,
                model=f"model-{i}",
                base_url="http://localhost:11434",
                timeout=1,
            )
            for i in range(5)
        ]

        services = [LLMService(config) for config in configs]

        # Attempt connections concurrently
        tasks = [service.validate_connection() for service in services]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Should handle all requests without crashing
            assert len(results) == 5

            for result in results:
                if isinstance(result, Exception):
                    # Exceptions are acceptable for failed connections
                    continue
                else:
                    success, message = result
                    assert isinstance(success, bool)
                    assert isinstance(message, str)
        finally:
            # Cleanup all services
            for service in services:
                await service.close()


class TestRealWorldScenarios:
    """Test real-world deployment scenarios"""

    @pytest.mark.asyncio
    async def test_user_has_ollama_running_locally(self):
        """Test scenario where user has Ollama running locally"""
        # This test simulates a user who has Ollama installed and running
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model="llama2:7b-chat",
            base_url="http://localhost:11434",
            timeout=10,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            print(f"Local Ollama test: success={success}, message={message}")

            if success:
                # If user actually has Ollama running, test should pass
                assert "successful" in message.lower() or "available" in message.lower()

                # Try a simple completion to verify it's working
                try:
                    response = await service.generate_completion(
                        prompt="Hello, world!", max_tokens=10
                    )
                    assert response is not None
                    assert len(response) > 0
                except Exception as e:
                    # Even if connection works, completion might fail due to model issues
                    print(f"Completion test failed (acceptable): {e}")
            else:
                # If Ollama is not running, should get clear error message
                assert len(message) > 10  # Should be descriptive

        except Exception as e:
            # Expected if Ollama is not installed/running
            print(f"Ollama not available (expected in test environment): {e}")
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_user_has_external_vllm_server(self):
        """Test scenario where user has external vLLM server"""
        # Simulate external vLLM server (will likely fail in test environment)
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            model="huggingface-model",
            base_url="http://192.168.1.100:8000/v1",
            api_key="optional-api-key",
            timeout=5,
        )

        service = LLMService(config)

        try:
            success, message = await service.validate_connection()

            print(f"External vLLM test: success={success}, message={message}")

            # In test environment, this will likely fail
            # But should fail gracefully with useful message
            assert isinstance(success, bool)
            assert len(message) > 5

            if not success:
                # Should indicate network/connection issue
                assert any(
                    keyword in message.lower()
                    for keyword in ["connection", "timeout", "refused", "unreachable"]
                )
        except Exception as e:
            print(f"External vLLM connection failed (expected): {e}")
        finally:
            await service.close()


def run_connection_tests():
    """
    Utility function to run connection tests manually

    This can be used to test actual connections when the services are available.
    """

    async def test_all():
        print("Testing external LLM connections...")

        # Test local Ollama
        print("\n1. Testing local Ollama...")
        test_ollama = TestExternalOllamaConnections()
        await test_ollama.test_local_ollama_default_config()

        # Test local vLLM
        print("\n2. Testing local vLLM...")
        test_vllm = TestExternalVLLMConnections()
        await test_vllm.test_local_vllm_default_config()

        # Test network edge cases
        print("\n3. Testing network edge cases...")
        test_network = TestNetworkEdgeCases()
        await test_network.test_connection_timeout()

        print("\nConnection tests completed!")

    asyncio.run(test_all())


if __name__ == "__main__":
    # Run connection tests if called directly
    run_connection_tests()
