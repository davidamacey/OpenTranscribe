---
sidebar_position: 3
---

# Testing

OpenTranscribe has comprehensive testing at multiple levels: unit tests, integration tests, and end-to-end browser tests.

## Test Structure

```
backend/tests/
├── conftest.py              # Shared fixtures for unit/integration tests
├── api/endpoints/           # API endpoint tests
├── e2e/                     # End-to-end browser tests
│   ├── conftest.py          # E2E fixtures
│   ├── test_login.py        # Login tests (~50 tests)
│   ├── test_registration.py # Registration tests (~35 tests)
│   └── test_auth_flow.py    # Combined auth flow tests
└── test_*.py                # Other unit tests
```

## Running Tests

### Prerequisites

```bash
# Activate virtual environment
source backend/venv/bin/activate

# Install test dependencies (if needed)
pip install pytest pytest-asyncio pytest-cov pytest-playwright
playwright install chromium
```

### Unit Tests

Unit tests run against the backend without requiring the full dev environment:

```bash
# Run all unit tests
pytest backend/tests/ --ignore=backend/tests/e2e/ -v

# Run specific test file
pytest backend/tests/test_auth_config_service.py -v

# Run with coverage
pytest backend/tests/ --ignore=backend/tests/e2e/ --cov=app -v
```

### E2E Tests

End-to-end tests require the dev environment running:

```bash
# Start dev environment
./opentr.sh start dev

# Run all E2E tests (headless)
pytest backend/tests/e2e/ -v

# Run with visible browser (for debugging)
DISPLAY=:13 pytest backend/tests/e2e/ -v --headed

# Run specific test
pytest backend/tests/e2e/test_login.py::TestLoginSuccess -v
```

## E2E Test Categories

### Login Tests

| Test Class | Description |
|------------|-------------|
| `TestLoginFormValidation` | Required field validation |
| `TestLoginSuccess` | Successful login scenarios |
| `TestLoginFailure` | Failed login scenarios |
| `TestLoginSecurity` | Password hiding, rate limiting |
| `TestLoginSession` | Session persistence |
| `TestLoginUI` | UI elements verification |
| `TestLoginAccessibility` | Keyboard navigation, labels |

### Registration Tests

| Test Class | Description |
|------------|-------------|
| `TestRegistrationFormValidation` | All fields required |
| `TestUsernameValidation` | Username constraints |
| `TestEmailValidation` | Email format validation |
| `TestPasswordValidation` | Password complexity rules |
| `TestDuplicatePrevention` | Duplicate email/username |
| `TestRegistrationSuccess` | Success flow |
| `TestRegistrationUI` | UI elements |

## Writing Tests

### Unit Test Example

```python
import pytest
from fastapi.testclient import TestClient

def test_login_success(client, normal_user):
    """Test successful login returns tokens."""
    response = client.post(
        "/api/auth/token",
        data={"username": normal_user.email, "password": "password123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
```

### E2E Test Example

```python
import pytest
from playwright.sync_api import Page, expect

class TestMyFeature:
    def test_feature_works(self, authenticated_page: Page):
        """Test feature with logged in user."""
        authenticated_page.click("#feature-button")
        authenticated_page.wait_for_selector("#result")
        expect(authenticated_page.locator("#result")).to_be_visible()
```

## Available Fixtures

### Unit Test Fixtures

| Fixture | Description |
|---------|-------------|
| `db_session` | Database session with transaction rollback |
| `client` | FastAPI TestClient |
| `normal_user` | Created normal user |
| `admin_user` | Created admin user |
| `user_token_headers` | Auth headers for normal user |
| `admin_token_headers` | Auth headers for admin user |

### E2E Test Fixtures

| Fixture | Description |
|---------|-------------|
| `page` | Fresh Playwright page |
| `login_page` | Page navigated to login |
| `authenticated_page` | Already logged in as admin |
| `auth_helper` | Login/logout/register helper |
| `api_helper` | Backend API call helper |
| `console_errors` | Captured browser console errors |
| `base_url` | Frontend URL (localhost:5173) |
| `backend_url` | Backend URL (localhost:5174) |

## Browser Automation (Claude Code)

For ad-hoc browser testing and debugging, Claude Code can use:

```bash
# Open browser and take screenshot
node ~/bin/browser-tools/browse.js http://localhost:5173

# With visible browser on XRDP
node ~/bin/browser-tools/browse.js http://localhost:5173 --display=:13

# Perform actions
node ~/bin/browser-tools/browse.js http://localhost:5173 \
  'fill:#email:admin@example.com' \
  'fill:#password:password' \
  'click:button[type=submit]' \
  'screenshot:result'
```

## Test Credentials

- **Admin user:** `admin@example.com` / `password`
- **Test users:** Created with unique UUIDs to avoid conflicts

## CI/CD Integration

```yaml
# Example GitHub Actions workflow
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    - name: Run unit tests
      run: |
        pip install -r requirements.txt
        pytest backend/tests/ --ignore=backend/tests/e2e/ -v
```

E2E tests are typically run separately as they require the full environment.

## Debugging Tips

1. **Use `--headed` flag** to watch browser tests
2. **Add `page.wait_for_timeout(5000)`** to pause and inspect
3. **Check `~/bin/browser-tools/screenshots/`** for screenshots
4. **Use `--screenshot only-on-failure`** for failed test screenshots
5. **Check browser console** with `console_errors` fixture
