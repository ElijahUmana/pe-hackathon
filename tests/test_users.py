"""Tests for the /users CRUD endpoints."""



# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------

def test_list_users_empty(client):
    resp = client.get("/users")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_users_returns_created_users(client):
    client.post("/users", json={"username": "alice", "email": "alice@example.com"})
    client.post("/users", json={"username": "bob", "email": "bob@example.com"})
    resp = client.get("/users")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2
    usernames = {u["username"] for u in data}
    assert usernames == {"alice", "bob"}


# ---------------------------------------------------------------------------
# Get user by ID
# ---------------------------------------------------------------------------

def test_get_user_by_id(client):
    create_resp = client.post(
        "/users", json={"username": "charlie", "email": "charlie@example.com"}
    )
    user_id = create_resp.get_json()["id"]
    resp = client.get(f"/users/{user_id}")
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "charlie"


def test_get_nonexistent_user_404(client):
    resp = client.get("/users/99999")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------

def test_create_user_valid(client):
    resp = client.post("/users", json={"username": "dave", "email": "dave@example.com"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["username"] == "dave"
    assert data["email"] == "dave@example.com"
    assert "id" in data


def test_create_user_missing_username(client):
    resp = client.post("/users", json={"email": "nousername@example.com"})
    assert resp.status_code == 400


def test_create_user_missing_email(client):
    resp = client.post("/users", json={"username": "noemail"})
    assert resp.status_code == 400


def test_create_user_empty_username(client):
    resp = client.post("/users", json={"username": "", "email": "empty@example.com"})
    assert resp.status_code == 400


def test_create_user_empty_email(client):
    resp = client.post("/users", json={"username": "emptyemail", "email": ""})
    assert resp.status_code == 400


def test_create_user_invalid_email(client):
    resp = client.post("/users", json={"username": "bademail", "email": "not-an-email"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_create_user_duplicate_username(client):
    client.post("/users", json={"username": "dupeuser", "email": "a@example.com"})
    resp = client.post("/users", json={"username": "dupeuser", "email": "b@example.com"})
    assert resp.status_code == 409


def test_create_user_duplicate_email(client):
    client.post("/users", json={"username": "user1", "email": "same@example.com"})
    resp = client.post("/users", json={"username": "user2", "email": "same@example.com"})
    assert resp.status_code == 409


def test_create_user_non_json_body(client):
    resp = client.post("/users", data="not json", content_type="text/plain")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Update user
# ---------------------------------------------------------------------------

def test_update_user(client):
    create_resp = client.post("/users", json={"username": "editable", "email": "edit@example.com"})
    user_id = create_resp.get_json()["id"]

    resp = client.put(f"/users/{user_id}", json={"username": "edited"})
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "edited"


def test_update_user_email(client):
    create_resp = client.post(
        "/users", json={"username": "emailedit", "email": "old@example.com"}
    )
    user_id = create_resp.get_json()["id"]
    resp = client.put(f"/users/{user_id}", json={"email": "new@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "new@example.com"


def test_update_user_invalid_email(client):
    create_resp = client.post(
        "/users", json={"username": "emailval", "email": "val@example.com"}
    )
    user_id = create_resp.get_json()["id"]
    resp = client.put(f"/users/{user_id}", json={"email": "bad-email"})
    assert resp.status_code == 400


def test_update_nonexistent_user(client):
    resp = client.put("/users/99999", json={"username": "ghost"})
    assert resp.status_code == 404


def test_update_user_empty_username(client):
    create_resp = client.post(
        "/users", json={"username": "empupd", "email": "empupd@example.com"}
    )
    user_id = create_resp.get_json()["id"]
    resp = client.put(f"/users/{user_id}", json={"username": ""})
    assert resp.status_code == 400


def test_update_user_non_json(client):
    create_resp = client.post(
        "/users", json={"username": "nonjsonupd", "email": "nonjsonupd@example.com"}
    )
    user_id = create_resp.get_json()["id"]
    resp = client.put(f"/users/{user_id}", data="text", content_type="text/plain")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Delete user
# ---------------------------------------------------------------------------

def test_delete_user(client):
    create_resp = client.post(
        "/users", json={"username": "deletable", "email": "del@example.com"}
    )
    user_id = create_resp.get_json()["id"]
    resp = client.delete(f"/users/{user_id}")
    assert resp.status_code == 204

    # Confirm gone
    resp = client.get(f"/users/{user_id}")
    assert resp.status_code == 404


def test_delete_nonexistent_user(client):
    resp = client.delete("/users/99999")
    assert resp.status_code == 404
