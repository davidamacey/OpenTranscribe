# E2E Tests for OpenTranscribe

End-to-end tests using pytest-playwright to verify frontend and backend work together through real browser automation.

## Prerequisites

1. **Dev environment running:**
   ```bash
   ./opentr.sh start dev
   ```

2. **Python venv with dependencies:**
   ```bash
   source backend/venv/bin/activate
   pip install pytest-playwright
   playwright install chromium
   ```

3. **Services accessible:**
   - Frontend: http://localhost:5173
   - Backend: http://localhost:5174

## Running Tests

### Basic Usage

```bash
# Activate venv
source backend/venv/bin/activate

# Run all E2E tests (headless)
pytest backend/tests/e2e/ -v

# Run specific test file
pytest backend/tests/e2e/test_login.py -v

# Run specific test class
pytest backend/tests/e2e/test_login.py::TestLoginSuccess -v

# Run specific test
pytest backend/tests/e2e/test_login.py::TestLoginSuccess::test_login_with_email -v
```

### With Visible Browser (XRDP)

If you have XRDP set up, you can watch the tests run:

```bash
# Find your XRDP display
ls /tmp/.X11-unix/  # Look for X13 or similar

# Run with visible browser
DISPLAY=:13 pytest backend/tests/e2e/ -v --headed
```

### Additional Options

```bash
# Screenshot on failure
pytest backend/tests/e2e/ -v --screenshot only-on-failure

# Slow down for debugging (100ms between actions)
pytest backend/tests/e2e/ -v --headed --slowmo 100

# Run tests marked as slow
pytest backend/tests/e2e/ -v -m slow

# Skip slow tests
pytest backend/tests/e2e/ -v -m "not slow"
```

## Test Structure

```
backend/tests/e2e/
├── conftest.py           # Shared fixtures
├── pytest.ini            # E2E-specific pytest config
├── README.md             # This file
├── test_auth_flow.py     # Combined auth flow tests
├── test_login.py         # Comprehensive login tests
└── test_registration.py  # Comprehensive registration tests
```

## Available Fixtures

### `login_page`
A page navigated to the login URL, ready for input.

```python
def test_example(self, login_page: Page):
    login_page.fill("#email", "user@example.com")
    login_page.fill("#password", "password")
    login_page.click("button[type=submit]")
```

### `authenticated_page`
A page already logged in as admin user.

```python
def test_example(self, authenticated_page: Page):
    # Already logged in, can interact with protected pages
    authenticated_page.click(".user-button")
```

### `auth_helper`
Helper class for authentication operations.

```python
def test_example(self, auth_helper):
    success = auth_helper.login("user@example.com", "password")
    auth_helper.logout()
    auth_helper.register("username", "email@example.com", "password")
```

### `api_helper`
Helper for making backend API calls alongside browser tests.

```python
def test_example(self, api_helper):
    api_helper.login("admin@example.com", "password")
    user_data = api_helper.get("/api/users/me")
```

### `console_errors`
Captures browser console errors during test.

```python
def test_no_errors(self, page: Page, console_errors: list):
    page.goto("http://localhost:5173")
    page.wait_for_timeout(2000)
    assert len(console_errors) == 0
```

### `base_url` / `backend_url`
URLs for frontend and backend.

```python
def test_example(self, page: Page, base_url: str, backend_url: str):
    page.goto(f"{base_url}/login")
    # base_url = http://localhost:5173
    # backend_url = http://localhost:5174
```

## Test Categories

### Login Tests (`test_login.py`)

| Class | Tests | Description |
|-------|-------|-------------|
| `TestLoginFormValidation` | 3 | Required field validation |
| `TestLoginSuccess` | 4 | Successful login scenarios |
| `TestLoginFailure` | 5 | Failed login scenarios |
| `TestLoginSecurity` | 3 | Password hiding, rate limiting |
| `TestLoginSession` | 2 | Session persistence |
| `TestLoginUI` | 5 | UI elements verification |
| `TestAlternativeAuth` | 2 | Keycloak, PKI options |
| `TestLoginAccessibility` | 3 | Labels, keyboard navigation |
| `TestLoginConsoleErrors` | 2 | No JS errors |

### Registration Tests (`test_registration.py`)

| Class | Tests | Description |
|-------|-------|-------------|
| `TestRegistrationFormValidation` | 5 | All fields required |
| `TestUsernameValidation` | 3 | Username constraints |
| `TestEmailValidation` | 3 | Email format validation |
| `TestPasswordValidation` | 7 | Password complexity, mismatch |
| `TestDuplicatePrevention` | 2 | Duplicate email/username |
| `TestRegistrationSuccess` | 2 | Success flow, can login after |
| `TestRegistrationUI` | 4 | UI elements verification |

## Writing New Tests

### Basic Test Structure

```python
import pytest
from playwright.sync_api import Page, expect

class TestMyFeature:
    """Test description."""

    def test_something(self, page: Page, base_url: str):
        """Test specific behavior."""
        page.goto(f"{base_url}/some-page")
        page.wait_for_selector("#element", timeout=10000)

        page.fill("#input", "value")
        page.click("button")

        page.wait_for_timeout(2000)

        expect(page.locator("#result")).to_be_visible()
```

### Using Fixtures

```python
class TestWithAuth:
    def test_protected_feature(self, authenticated_page: Page):
        """Test that requires logged in user."""
        # Already logged in
        authenticated_page.click("#some-protected-button")
```

### Handling Async Operations

```python
def test_async_operation(self, page: Page, base_url: str):
    page.goto(base_url)

    # Wait for network to settle
    page.wait_for_load_state("networkidle")

    # Wait for specific element
    page.wait_for_selector("#async-content", timeout=30000)

    # Or wait with explicit timeout
    page.wait_for_timeout(2000)
```

## Test Credentials

- **Admin user:** `admin@example.com` / `password`
- **Test user creation:** Uses unique UUID-based emails to avoid conflicts

## Troubleshooting

### Tests fail with "element detached from DOM"
Add explicit waits after navigation:
```python
page.goto(url)
page.wait_for_load_state("networkidle")
page.wait_for_selector("#element")
```

### Browser doesn't open with --headed
Check DISPLAY environment variable:
```bash
echo $DISPLAY
ls /tmp/.X11-unix/
DISPLAY=:13 pytest ... --headed
```

### Timeout errors
Increase timeout or add explicit waits:
```python
page.wait_for_selector("#element", timeout=30000)
```

### Tests pass locally but fail in CI
E2E tests require the full dev environment running. In CI, either:
- Skip E2E tests: `pytest backend/tests/ --ignore=backend/tests/e2e/`
- Set up services in CI pipeline
