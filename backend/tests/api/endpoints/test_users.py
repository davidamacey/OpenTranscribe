def test_get_users(client, admin_token_headers):
    """Test listing all users (admin only endpoint)"""
    response = client.get("/api/users/", headers=admin_token_headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) > 0

    # Basic schema validation
    assert "id" in users[0]
    assert "email" in users[0]
    assert "full_name" in users[0]
    assert "is_active" in users[0]
    assert "role" in users[0]


def test_get_users_unauthorized(client, user_token_headers):
    """Test that regular users cannot list all users"""
    response = client.get("/api/users/", headers=user_token_headers)
    assert response.status_code in (401, 403)  # Either unauthorized or forbidden


def test_get_current_user(client, user_token_headers, normal_user):
    """Test getting current user info"""
    response = client.get("/api/users/me", headers=user_token_headers)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == normal_user.email
    assert user_data["full_name"] == normal_user.full_name
    assert user_data["id"] == normal_user.id


def test_update_current_user(client, user_token_headers):
    """Test updating current user info"""
    update_data = {"full_name": "Updated Name"}
    response = client.put("/api/users/me", headers=user_token_headers, json=update_data)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["full_name"] == "Updated Name"


def test_get_user_by_id(client, admin_token_headers, normal_user):
    """Test getting user by ID (admin only)"""
    response = client.get(f"/api/users/{normal_user.id}", headers=admin_token_headers)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == normal_user.email
    assert user_data["id"] == normal_user.id


def test_get_user_by_id_unauthorized(client, user_token_headers, admin_user):
    """Test that regular users cannot get other users by ID"""
    response = client.get(f"/api/users/{admin_user.id}", headers=user_token_headers)
    assert response.status_code in (401, 403)  # Either unauthorized or forbidden


def test_update_user(client, admin_token_headers, normal_user):
    """Test updating a user (admin only)"""
    update_data = {"full_name": "Admin Updated User", "is_active": False}
    response = client.put(
        f"/api/users/{normal_user.id}", headers=admin_token_headers, json=update_data
    )
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["full_name"] == "Admin Updated User"
    assert user_data["is_active"] is False


def test_update_user_unauthorized(client, user_token_headers, admin_user):
    """Test that regular users cannot update other users"""
    update_data = {"full_name": "Should Fail"}
    response = client.put(
        f"/api/users/{admin_user.id}", headers=user_token_headers, json=update_data
    )
    assert response.status_code in (401, 403)  # Either unauthorized or forbidden


def test_delete_user(client, admin_token_headers, normal_user, db_session):
    """Test deleting a user (admin only)"""
    response = client.delete(
        f"/api/users/{normal_user.id}", headers=admin_token_headers
    )
    assert response.status_code == 204

    # Verify the user is deleted from the database
    from app.models.user import User

    deleted_user = db_session.query(User).filter(User.id == normal_user.id).first()
    assert deleted_user is None


def test_delete_user_unauthorized(client, user_token_headers, admin_user):
    """Test that regular users cannot delete other users"""
    response = client.delete(f"/api/users/{admin_user.id}", headers=user_token_headers)
    assert response.status_code in (401, 403)  # Either unauthorized or forbidden
