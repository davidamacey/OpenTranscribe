"""Tag endpoint tests."""


def test_list_tags(client, user_token_headers):
    """Test listing all tags"""
    response = client.get("/api/tags", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_tags_unauthorized(client):
    """Test that unauthorized users cannot list tags"""
    response = client.get("/api/tags")
    assert response.status_code == 401  # Unauthorized


def test_create_tag(client, user_token_headers, db_session):
    """Test creating a new tag"""
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    tag_data = {"name": f"test_tag_{unique_id}"}
    response = client.post("/api/tags", headers=user_token_headers, json=tag_data)
    assert response.status_code == 200, f"Create tag failed: {response.json()}"
    tag = response.json()
    assert "uuid" in tag or "id" in tag
    assert tag["name"] == tag_data["name"]


def test_create_duplicate_tag(client, user_token_headers, db_session):
    """Test creating a duplicate tag returns existing tag"""
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    tag_data = {"name": f"duplicate_tag_{unique_id}"}

    # First create a tag
    first_response = client.post("/api/tags", headers=user_token_headers, json=tag_data)
    assert first_response.status_code == 200

    # Try to create the same tag again - should return existing tag
    response = client.post("/api/tags", headers=user_token_headers, json=tag_data)
    assert response.status_code == 200
