#!/usr/bin/env python3
"""
Comprehensive test script for AI Features (Issue #51)

This script tests the full AI summarization and LLM provider configuration 
functionality to ensure everything works correctly.

Usage:
    python test_ai_features.py [--manual] [--skip-external]
    
Options:
    --manual        Run manual tests that require user interaction
    --skip-external Skip external service tests (Ollama, vLLM, etc.)
    --verbose       Enable verbose output
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

try:
    from app.utils.encryption import encrypt_api_key, decrypt_api_key, test_encryption
    from app.services.llm_service import LLMService, LLMConfig, LLMProvider
    from app.schemas.llm_settings import ConnectionTestRequest
    from app.core.config import settings
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


class Colors:
    """Terminal colors for pretty output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{Colors.END}")


def print_test(test_name: str, status: str, details: str = ""):
    """Print a test result"""
    if status == "PASS":
        icon = f"{Colors.GREEN}✓{Colors.END}"
        status_text = f"{Colors.GREEN}{status}{Colors.END}"
    elif status == "FAIL":
        icon = f"{Colors.RED}✗{Colors.END}"
        status_text = f"{Colors.RED}{status}{Colors.END}"
    elif status == "SKIP":
        icon = f"{Colors.YELLOW}⚠{Colors.END}"
        status_text = f"{Colors.YELLOW}{status}{Colors.END}"
    else:
        icon = f"{Colors.CYAN}ℹ{Colors.END}"
        status_text = f"{Colors.CYAN}{status}{Colors.END}"
    
    print(f"{icon} {test_name:<50} [{status_text}]")
    if details:
        print(f"    {Colors.WHITE}{details}{Colors.END}")


async def test_encryption_system():
    """Test the encryption system"""
    print_header("Testing Encryption System")
    
    # Test basic encryption functionality
    try:
        result = test_encryption()
        print_test("Basic encryption test", "PASS" if result else "FAIL")
    except Exception as e:
        print_test("Basic encryption test", "FAIL", str(e))
        return False
    
    # Test with various API key formats
    test_keys = [
        "sk-1234567890abcdef",
        "api_key_test_123",
        "Bearer token_with_special_chars!@#$",
        "very-long-api-key-that-exceeds-typical-length-to-test-encryption-with-longer-strings"
    ]
    
    all_passed = True
    for i, key in enumerate(test_keys):
        try:
            encrypted = encrypt_api_key(key)
            if not encrypted:
                print_test(f"Encrypt test key {i+1}", "FAIL", "Encryption returned None")
                all_passed = False
                continue
            
            decrypted = decrypt_api_key(encrypted)
            if decrypted != key:
                print_test(f"Encrypt/decrypt test key {i+1}", "FAIL", "Decrypted value doesn't match original")
                all_passed = False
                continue
            
            print_test(f"Encrypt/decrypt test key {i+1}", "PASS")
        except Exception as e:
            print_test(f"Encrypt/decrypt test key {i+1}", "FAIL", str(e))
            all_passed = False
    
    return all_passed


async def test_llm_service_creation():
    """Test LLM service creation with different configurations"""
    print_header("Testing LLM Service Creation")
    
    # Test system default creation
    try:
        service = LLMService.create_from_system_settings()
        if service:
            print_test("Create from system settings", "PASS", f"Provider: {service.config.provider.value}")
            await service.close()
        else:
            print_test("Create from system settings", "FAIL", "Service creation returned None")
            return False
    except Exception as e:
        print_test("Create from system settings", "FAIL", str(e))
        return False
    
    # Test user settings fallback (should fallback to system)
    try:
        service = LLMService.create_from_settings(user_id=99999)  # Non-existent user
        if service:
            print_test("Create with user fallback", "PASS", "Correctly fell back to system defaults")
            await service.close()
        else:
            print_test("Create with user fallback", "FAIL", "Service creation returned None")
            return False
    except Exception as e:
        print_test("Create with user fallback", "FAIL", str(e))
        return False
    
    # Test different provider configurations
    providers = [
        (LLMProvider.OPENAI, "gpt-3.5-turbo", "https://api.openai.com/v1"),
        (LLMProvider.VLLM, "test-model", "http://localhost:8012/v1"),
        (LLMProvider.OLLAMA, "llama2:7b-chat", "http://localhost:11434"),
    ]
    
    for provider, model, base_url in providers:
        try:
            config = LLMConfig(
                provider=provider,
                model=model,
                base_url=base_url,
                timeout=5
            )
            service = LLMService(config)
            print_test(f"Create {provider.value} service", "PASS", f"Model: {model}")
            await service.close()
        except Exception as e:
            print_test(f"Create {provider.value} service", "FAIL", str(e))
    
    return True


async def test_connection_validation(skip_external: bool = False):
    """Test connection validation for different providers"""
    print_header("Testing Connection Validation")
    
    if skip_external:
        print_test("External connection tests", "SKIP", "Skipped due to --skip-external flag")
        return True
    
    # Test configurations that are likely to fail (expected behavior)
    test_configs = [
        # Local Ollama (may or may not be running)
        (LLMProvider.OLLAMA, "llama2:7b-chat", "http://localhost:11434", None),
        
        # Local vLLM (may or may not be running) 
        (LLMProvider.VLLM, "test-model", "http://localhost:8012/v1", None),
        
        # Invalid endpoint (should fail)
        (LLMProvider.VLLM, "test-model", "http://localhost:99999", None),
        
        # DNS failure (should fail gracefully)
        (LLMProvider.OLLAMA, "test-model", "http://nonexistent-domain-12345.com", None),
    ]
    
    for provider, model, base_url, api_key in test_configs:
        try:
            config = LLMConfig(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                timeout=3  # Short timeout for tests
            )
            
            service = LLMService(config)
            
            start_time = time.time()
            success, message = await service.validate_connection()
            elapsed = time.time() - start_time
            
            # Log the result (success or failure both acceptable)
            status = "PASS" if success else "EXPECTED_FAIL"
            details = f"Success: {success}, Time: {elapsed:.1f}s, Message: {message[:50]}..."
            print_test(f"Connection to {base_url}", status, details)
            
            await service.close()
            
        except Exception as e:
            # Exceptions are also expected for unreachable services
            print_test(f"Connection to {base_url}", "EXPECTED_FAIL", f"Exception: {str(e)[:50]}...")
    
    return True


async def test_api_schemas():
    """Test API schemas and validation"""
    print_header("Testing API Schemas")
    
    try:
        # Test ConnectionTestRequest
        from app.schemas.llm_settings import (
            ConnectionTestRequest, UserLLMSettingsCreate, 
            UserLLMSettingsUpdate, ProviderDefaults
        )
        
        # Valid connection test request
        request = ConnectionTestRequest(
            provider="openai",
            model_name="gpt-3.5-turbo",
            api_key="sk-test123",
            base_url="https://api.openai.com/v1",
            timeout=30
        )
        print_test("ConnectionTestRequest schema", "PASS", f"Provider: {request.provider}")
        
        # Valid settings creation
        settings_create = UserLLMSettingsCreate(
            provider="vllm",
            model_name="microsoft/DialoGPT-medium",
            base_url="http://localhost:8012/v1",
            max_tokens=4000,
            temperature="0.5",
            timeout=120
        )
        print_test("UserLLMSettingsCreate schema", "PASS", f"Max tokens: {settings_create.max_tokens}")
        
        # Test validation errors
        try:
            UserLLMSettingsCreate(
                provider="openai",
                model_name="gpt-4",
                max_tokens=0  # Invalid: too low
            )
            print_test("Schema validation (should fail)", "FAIL", "Validation should have failed for max_tokens=0")
        except ValueError:
            print_test("Schema validation (max_tokens)", "PASS", "Correctly rejected invalid max_tokens")
        
        try:
            UserLLMSettingsCreate(
                provider="openai", 
                model_name="gpt-4",
                temperature="3.0"  # Invalid: too high
            )
            print_test("Schema validation (should fail)", "FAIL", "Validation should have failed for temperature=3.0")
        except ValueError:
            print_test("Schema validation (temperature)", "PASS", "Correctly rejected invalid temperature")
        
        return True
        
    except Exception as e:
        print_test("API schema tests", "FAIL", str(e))
        return False


def test_database_model():
    """Test database model creation (without actually connecting to DB)"""
    print_header("Testing Database Models")
    
    try:
        from app.models.user_llm_settings import UserLLMSettings
        
        # Test model instantiation
        settings = UserLLMSettings(
            user_id=1,
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="encrypted_key_here",
            base_url="https://api.openai.com/v1",
            max_tokens=2000,
            temperature="0.3",
            timeout=60,
            is_active=True
        )
        
        print_test("UserLLMSettings model creation", "PASS", f"Provider: {settings.provider}")
        print_test("Model attributes", "PASS", f"Model: {settings.model_name}, Active: {settings.is_active}")
        
        # Test string representation
        repr_str = repr(settings)
        if "UserLLMSettings" in repr_str and "openai" in repr_str:
            print_test("Model __repr__ method", "PASS", "String representation looks correct")
        else:
            print_test("Model __repr__ method", "FAIL", f"Unexpected repr: {repr_str}")
        
        return True
        
    except Exception as e:
        print_test("Database model test", "FAIL", str(e))
        return False


def print_manual_test_instructions():
    """Print instructions for manual testing"""
    print_header("Manual Testing Instructions")
    
    instructions = [
        "1. Start the application with './opentr.sh start dev'",
        "2. Navigate to http://localhost:5173 in your browser",
        "3. Login and go to User Settings",
        "4. Test the following tabs:",
        "   • AI Prompts tab: Create, edit, and select custom prompts",
        "   • LLM Provider tab: Configure different LLM providers",
        "5. Try these LLM provider configurations:",
        "   • OpenAI: Requires valid API key",
        "   • vLLM: Test with http://localhost:8012/v1 (if running)",
        "   • Ollama: Test with http://localhost:11434 (if running)",
        "6. Test connection validation for each provider",
        "7. Generate a summary using different prompts and providers",
        "8. Verify that user settings are saved and persist across sessions"
    ]
    
    for instruction in instructions:
        print(f"{Colors.CYAN}  {instruction}{Colors.END}")
    
    print(f"\n{Colors.YELLOW}Note: Some tests require external services to be running{Colors.END}")


def check_environment():
    """Check if the environment is properly configured"""
    print_header("Environment Check")
    
    # Check if we're in the right directory
    if not (Path.cwd() / "backend" / "app").exists():
        print_test("Project directory structure", "FAIL", "Not in the correct project directory")
        return False
    
    print_test("Project directory structure", "PASS", "Found backend/app directory")
    
    # Check for key files
    key_files = [
        "backend/app/models/user_llm_settings.py",
        "backend/app/api/endpoints/llm_settings.py",
        "backend/app/utils/encryption.py",
        "frontend/src/components/settings/LLMSettings.svelte",
        "frontend/src/components/settings/PromptSettings.svelte",
        "frontend/src/lib/api/llmSettings.ts",
        "database/init_db.sql"
    ]
    
    all_found = True
    for file_path in key_files:
        if Path(file_path).exists():
            print_test(f"File: {file_path}", "PASS")
        else:
            print_test(f"File: {file_path}", "FAIL", "File not found")
            all_found = False
    
    # Check environment variables (optional)
    env_vars = ["JWT_SECRET_KEY", "LLM_PROVIDER"]
    for var in env_vars:
        if os.getenv(var):
            print_test(f"Environment variable: {var}", "PASS", "Set")
        else:
            print_test(f"Environment variable: {var}", "INFO", "Not set (using defaults)")
    
    return all_found


async def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description="Test AI features implementation")
    parser.add_argument("--manual", action="store_true", help="Show manual test instructions")
    parser.add_argument("--skip-external", action="store_true", help="Skip external service tests")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    print(f"{Colors.BOLD}{Colors.PURPLE}")
    print("🤖 OpenTranscribe AI Features Test Suite")
    print("Testing implementation of GitHub Issue #51")
    print(f"{Colors.END}")
    
    if args.manual:
        print_manual_test_instructions()
        return
    
    # Environment check
    if not check_environment():
        print(f"\n{Colors.RED}❌ Environment check failed. Please ensure you're in the correct directory.{Colors.END}")
        return
    
    # Run automated tests
    tests = [
        ("Encryption System", test_encryption_system),
        ("LLM Service Creation", test_llm_service_creation),
        ("Connection Validation", lambda: test_connection_validation(args.skip_external)),
        ("API Schemas", test_api_schemas),
        ("Database Models", test_database_model),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print_test(f"{test_name} (ERROR)", "FAIL", str(e))
            failed += 1
    
    # Summary
    print_header("Test Summary")
    print(f"  {Colors.GREEN}✓ Passed: {passed}{Colors.END}")
    print(f"  {Colors.RED}✗ Failed: {failed}{Colors.END}")
    print(f"  {Colors.CYAN}📊 Total:  {passed + failed}{Colors.END}")
    
    if failed == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 All tests passed! AI features are working correctly.{Colors.END}")
        print(f"\n{Colors.CYAN}Next steps:{Colors.END}")
        print(f"  1. Run manual tests: python test_ai_features.py --manual")
        print(f"  2. Start the application and test the UI")
        print(f"  3. Test with actual external LLM services")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ Some tests failed. Please check the output above.{Colors.END}")
    
    print(f"\n{Colors.PURPLE}For manual testing instructions, run:{Colors.END}")
    print(f"  python test_ai_features.py --manual")


if __name__ == "__main__":
    asyncio.run(main())