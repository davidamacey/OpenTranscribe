def test_login_success(client, normal_user):
    """Test successful login returns JWT token"""
    login_data = {"username": "user@example.com", "password": "password123"}
    response = client.post("/api/auth/token", data=login_data)
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert "token_type" in tokens
    assert tokens["token_type"] == "bearer"  # noqa: S105 - OAuth token type, not a password


def test_login_invalid_credentials(client, normal_user):
    """Test login with invalid credentials fails"""
    login_data = {"username": "user@example.com", "password": "wrongpassword"}
    response = client.post("/api/auth/token", data=login_data)
    assert response.status_code == 401  # Unauthorized


def test_login_nonexistent_user(client):
    """Test login with non-existent user fails"""
    login_data = {"username": "nonexistent@example.com", "password": "password123"}
    response = client.post("/api/auth/token", data=login_data)
    assert response.status_code == 401  # Unauthorized


def test_current_user(client, user_token_headers):
    """Test get current user endpoint with valid token"""
    response = client.get("/api/auth/me", headers=user_token_headers)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == "user@example.com"


def test_current_user_no_token(client):
    """Test get current user endpoint with no token fails"""
    response = client.get("/api/auth/me")
    assert response.status_code == 401  # Unauthorized
