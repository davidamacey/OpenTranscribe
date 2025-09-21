import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set testing environment flag and disable external services in tests
os.environ["TESTING"] = "True"
os.environ["SKIP_CELERY"] = "True"
os.environ["SKIP_S3"] = "True"
os.environ["SKIP_REDIS"] = "True"
os.environ["SKIP_WEBSOCKET"] = "True"
os.environ["SKIP_OPENSEARCH"] = "True"

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.base import get_db
from app.main import app
from app.models.user import User

# Create in-memory SQLite database for testing
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Fixture that provides a SQLAlchemy session for tests"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


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

    # Reset dependency overrides after test
    app.dependency_overrides = {}


@pytest.fixture(scope="function")
def normal_user(db_session):
    """Fixture that creates a normal user in the test database"""
    user = User(
        email="user@example.com",
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
    """Fixture that creates an admin user in the test database"""
    user = User(
        email="admin@example.com",
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
    """Fixture that returns auth headers for a regular user"""
    # Using form-encoded data for OAuth2 password flow
    response = client.post(
        "/api/auth/token",
        data={"username": normal_user.email, "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    tokens = response.json()
    access_token = tokens["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture(scope="function")
def admin_token_headers(client, admin_user):
    """Fixture that returns auth headers for an admin user"""
    # Using form-encoded data for OAuth2 password flow
    response = client.post(
        "/api/auth/token",
        data={"username": admin_user.email, "password": "adminpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    tokens = response.json()
    access_token = tokens["access_token"]
    return {"Authorization": f"Bearer {access_token}"}
