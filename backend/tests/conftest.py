import os
import sys
import tempfile
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend directory to Python path for imports
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Read database credentials from .env file without loading all variables
# This avoids polluting the environment with variables that aren't in Settings
_project_root = _backend_dir.parent
_env_file = _project_root / ".env"
_env_values = {}
if _env_file.exists():
    _env_values = dotenv_values(_env_file)

# Set only the database credentials we need from .env
_db_vars = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]
for _var in _db_vars:
    if _var in _env_values:
        os.environ[_var] = _env_values[_var]

# Create temporary directories for testing
_test_temp_dir = tempfile.mkdtemp(prefix="opentranscribe_test_")
_test_data_dir = os.path.join(_test_temp_dir, "data")
_test_upload_dir = os.path.join(_test_data_dir, "uploads")
_test_models_dir = os.path.join(_test_temp_dir, "models")
_test_temp_subdir = os.path.join(_test_temp_dir, "temp")

# Create all directories
for _dir in [_test_data_dir, _test_upload_dir, _test_models_dir, _test_temp_subdir]:
    os.makedirs(_dir, exist_ok=True)

# Set testing environment flag and disable external services in tests
os.environ["TESTING"] = "True"
os.environ["SKIP_CELERY"] = "True"
os.environ["SKIP_S3"] = "True"
os.environ["SKIP_REDIS"] = "True"
os.environ["SKIP_WEBSOCKET"] = "True"
os.environ["SKIP_OPENSEARCH"] = "True"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # Disable rate limiting for tests

# Set paths to use temporary directories for testing (must be set before importing config)
os.environ["DATA_DIR"] = _test_data_dir
os.environ["MODELS_DIR"] = _test_models_dir
os.environ["TEMP_DIR"] = _test_temp_subdir

# Database connection for local testing - use localhost instead of Docker service name
# The .env file has POSTGRES_HOST=postgres (Docker service) but we need localhost
os.environ["POSTGRES_HOST"] = "localhost"
# Ensure we use the correct port (Docker exposes on 5176)
if "POSTGRES_PORT" not in os.environ or os.environ.get("POSTGRES_PORT") == "5432":
    os.environ["POSTGRES_PORT"] = "5176"

# Import app modules after setting environment variables (they check env during import)
from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.db.base import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

# Use PostgreSQL test database (same as main database but with test schema isolation)
# Models use PostgreSQL-specific types (JSONB) that SQLite doesn't support
SQLALCHEMY_TEST_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Fixture that provides a SQLAlchemy session for tests.

    Uses nested transactions (savepoints) for test isolation - all changes made during
    a test are rolled back at the end, leaving the database in its original state.

    This handles the case where the code under test calls commit() by using
    a savepoint that can be rolled back.
    """
    from sqlalchemy import event

    connection = engine.connect()
    transaction = connection.begin()

    # Create a session bound to this connection
    session = TestingSessionLocal(bind=connection)

    # Start a nested transaction (savepoint)
    session.begin_nested()

    # When the session commits, restart the nested transaction
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, trans):
        if trans.nested and not trans._parent.nested:
            # The savepoint was committed, start a new one
            session.begin_nested()

    try:
        yield session
    finally:
        # Remove the event listener
        event.remove(session, "after_transaction_end", restart_savepoint)
        session.close()
        # Rollback the outer transaction to undo all test changes
        try:
            if transaction.is_active:
                transaction.rollback()
        except Exception:
            pass
        connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Fixture that provides a FastAPI TestClient with test DB session"""

    # Override the get_db dependency to use test DB session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Create test client
    with TestClient(app) as test_client:
        yield test_client

    # Remove only our override (race-safe for parallel workers)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="function")
def normal_user(db_session):
    """Fixture that creates a normal user in the test database.

    Uses a unique UUID-based email to avoid conflicts between parallel tests.
    """
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    user = User(
        email=f"testuser_{unique_id}@example.com",
        full_name="Test User",
        hashed_password=get_password_hash("password123"),
        is_active=True,
        is_superuser=False,
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_user(db_session):
    """Fixture that creates an admin user in the test database.

    Uses a unique UUID-based email to avoid conflicts between parallel tests.
    """
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    user = User(
        email=f"testadmin_{unique_id}@example.com",
        full_name="Admin User",
        hashed_password=get_password_hash("adminpass"),
        is_active=True,
        is_superuser=True,
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def user_token_headers(client, normal_user):
    """Fixture that returns auth headers for a regular user."""
    # Using form-encoded data for OAuth2 password flow
    response = client.post(
        "/api/auth/token",
        data={"username": normal_user.email, "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, f"Login failed for {normal_user.email}: {response.json()}"
    tokens = response.json()
    access_token = tokens["access_token"]
    # Return headers along with the user email for tests that need to verify it
    headers = {"Authorization": f"Bearer {access_token}"}
    headers["_test_user_email"] = normal_user.email  # Metadata for tests
    return headers


@pytest.fixture(scope="function")
def admin_token_headers(client, admin_user):
    """Fixture that returns auth headers for an admin user."""
    # Using form-encoded data for OAuth2 password flow
    response = client.post(
        "/api/auth/token",
        data={"username": admin_user.email, "password": "adminpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, f"Login failed for {admin_user.email}: {response.json()}"
    tokens = response.json()
    access_token = tokens["access_token"]
    # Return headers along with the user email for tests that need to verify it
    headers = {"Authorization": f"Bearer {access_token}"}
    headers["_test_user_email"] = admin_user.email  # Metadata for tests
    return headers


@pytest.fixture(scope="function")
def super_admin_user(db_session):
    """Fixture that creates a super_admin user in the test database.

    Uses a unique UUID-based email to avoid conflicts between parallel tests.
    """
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    user = User(
        email=f"testsuperadmin_{unique_id}@example.com",
        full_name="Super Admin User",
        hashed_password=get_password_hash("superadminpass"),
        is_active=True,
        is_superuser=True,
        role="super_admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def super_admin_token_headers(client, super_admin_user):
    """Fixture that returns auth headers for a super_admin user."""
    response = client.post(
        "/api/auth/token",
        data={"username": super_admin_user.email, "password": "superadminpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, (
        f"Login failed for {super_admin_user.email}: {response.json()}"
    )
    tokens = response.json()
    access_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    headers["_test_user_email"] = super_admin_user.email
    return headers


# --- Fixture aliases for test_media_security.py and other tests ---


@pytest.fixture(scope="function")
def test_user(normal_user):
    """Alias for normal_user fixture."""
    return normal_user


@pytest.fixture(scope="function")
def auth_headers(user_token_headers):
    """Alias for user_token_headers fixture."""
    return user_token_headers


@pytest.fixture(scope="function")
def admin_auth_headers(admin_token_headers):
    """Alias for admin_token_headers fixture."""
    return admin_token_headers


@pytest.fixture(scope="function")
def other_user(db_session):
    """Create a second normal user for access-control tests."""
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    user = User(
        email=f"otheruser_{unique_id}@example.com",
        full_name="Other User",
        hashed_password=get_password_hash("otherpass123"),
        is_active=True,
        is_superuser=False,
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def other_user_auth_headers(client, other_user):
    """Auth headers for the other_user (second normal user)."""
    response = client.post(
        "/api/auth/token",
        data={"username": other_user.email, "password": "otherpass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, f"Login failed for {other_user.email}: {response.json()}"
    tokens = response.json()
    access_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    headers["_test_user_email"] = other_user.email
    return headers
