def test_admin_stats(client, admin_token_headers):
    """Test getting admin statistics"""
    response = client.get("/api/admin/stats", headers=admin_token_headers)
    assert response.status_code == 200
    stats = response.json()

    # Basic schema validation
    assert "users" in stats
    assert "total" in stats["users"]
    assert "files" in stats
    assert "system" in stats


def test_admin_stats_unauthorized(client, user_token_headers):
    """Test that regular users cannot access admin stats"""
    response = client.get("/api/admin/stats", headers=user_token_headers)
    assert response.status_code in (401, 403)  # Either unauthorized or forbidden


def test_admin_users_list(client, admin_token_headers, admin_user, normal_user):
    """Test admin users list endpoint"""
    response = client.get("/api/admin/users", headers=admin_token_headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)

    # There should be at least 2 users (normal and admin from fixtures)
    assert len(users) >= 2

    # Basic schema validation
    assert "id" in users[0]
    assert "email" in users[0]


def test_admin_users_create(client, admin_token_headers, db_session):
    """Test admin user creation endpoint"""
    new_user_data = {
        "email": "newuser@example.com",
        "password": "Password123",
        "full_name": "New Test User",
        "role": "user",
        "is_active": True,
        "is_superuser": False,
    }

    response = client.post("/api/admin/users", headers=admin_token_headers, json=new_user_data)
    assert response.status_code == 200
    user_data = response.json()

    # Check that the user was created properly
    assert user_data["email"] == new_user_data["email"]
    assert user_data["full_name"] == new_user_data["full_name"]
    assert user_data["role"] == new_user_data["role"]

    # Verify user exists in the database
    from app.models.user import User

    db_user = db_session.query(User).filter(User.email == new_user_data["email"]).first()
    assert db_user is not None
    assert db_user.email == new_user_data["email"]


def test_admin_users_delete(client, admin_token_headers, normal_user, db_session):
    """Test admin user deletion endpoint"""
    response = client.delete(f"/api/admin/users/{normal_user.id}", headers=admin_token_headers)
    assert response.status_code == 200
    assert response.json() == {"message": "User deleted successfully"}

    # Verify user was deleted from the database
    from app.models.user import User

    db_user = db_session.query(User).filter(User.id == normal_user.id).first()
    assert db_user is None
