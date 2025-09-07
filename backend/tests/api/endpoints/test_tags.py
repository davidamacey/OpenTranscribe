def test_list_tags(client, user_token_headers):
    """Test listing all tags"""
    response = client.get("/api/tags/", headers=user_token_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_tags_unauthorized(client):
    """Test that unauthorized users cannot list tags"""
    response = client.get("/api/tags/")
    assert response.status_code == 401  # Unauthorized


def test_create_tag(client, user_token_headers, db_session):
    """Test creating a new tag"""
    tag_data = {"name": "test_tag"}
    response = client.post("/api/tags/", headers=user_token_headers, json=tag_data)
    assert response.status_code == 200
    tag = response.json()
    assert "id" in tag
    assert tag["name"] == "test_tag"

    # Verify tag exists in the database
    from app.models.media import Tag

    db_tag = db_session.query(Tag).filter(Tag.name == "test_tag").first()
    assert db_tag is not None
    assert db_tag.name == "test_tag"


def test_create_duplicate_tag(client, user_token_headers, db_session):
    """Test creating a duplicate tag"""
    # First create a tag
    tag_data = {"name": "duplicate_tag"}
    client.post("/api/tags/", headers=user_token_headers, json=tag_data)

    # Try to create the same tag again
    response = client.post("/api/tags/", headers=user_token_headers, json=tag_data)
    # Should return the existing tag instead of error
    assert response.status_code == 200

    # Verify only one tag with that name exists in the database
    from app.models.media import Tag

    tag_count = db_session.query(Tag).filter(Tag.name == "duplicate_tag").count()
    assert tag_count == 1
