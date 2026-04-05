"""API contract edge-case tests.

Covers:
- Bulk upload edge cases (empty CSV, wrong columns, duplicate users)
- URL creation edge cases (integer username, empty title, very long URLs)
- Update edge cases (nonexistent, empty body, partial update)
- Redirect edge cases (query params in original URL, deleted URL redirect)
- Data type validation (integer for username, boolean for email, etc.)
"""

import io

from app.models.event import Event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(client, username="contractuser", email="contract@example.com"):
    resp = client.post("/users", json={"username": username, "email": email})
    return resp


def _create_url(client, url="https://example.com", user_id=None, title=None):
    payload = {"url": url}
    if user_id is not None:
        payload["user_id"] = user_id
    if title is not None:
        payload["title"] = title
    return client.post("/urls", json=payload)


def _upload_csv(client, csv_content, filename="users.csv"):
    data = {"file": (io.BytesIO(csv_content.encode("utf-8")), filename)}
    return client.post(
        "/users/bulk",
        data=data,
        content_type="multipart/form-data",
    )


# ---------------------------------------------------------------------------
# 1. Bulk Upload Edge Cases
# ---------------------------------------------------------------------------

class TestBulkUploadEdgeCases:
    def test_empty_csv_returns_zero_imported(self, client):
        """An empty CSV (headers only, no rows) should import 0 users."""
        resp = _upload_csv(client, "username,email\n")
        assert resp.status_code == 201
        assert resp.get_json()["imported"] == 0

    def test_csv_with_wrong_columns_imports_zero(self, client):
        """A CSV missing username/email columns should skip all rows since
        username and email are required fields."""
        csv = "first_name,last_name\nJohn,Doe\nJane,Smith\n"
        resp = _upload_csv(client, csv)
        assert resp.status_code == 201
        assert resp.get_json()["imported"] == 0

    def test_csv_with_duplicate_users(self, client):
        """Duplicate users in a CSV should be skipped (IntegrityError handled)."""
        csv = (
            "username,email\n"
            "bulkdup,bulkdup@example.com\n"
            "bulkdup,bulkdup2@example.com\n"
        )
        resp = _upload_csv(client, csv)
        assert resp.status_code == 201
        # First row succeeds, second fails on duplicate username
        assert resp.get_json()["imported"] == 1

    def test_bulk_upload_no_file(self, client):
        """POST /users/bulk without a file returns 400."""
        resp = client.post(
            "/users/bulk",
            data={},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_csv_with_extra_columns_still_works(self, client):
        """Extra columns in the CSV should be ignored; valid rows still import."""
        csv = "username,email,age,phone\nextrauser,extra@example.com,25,555-1234\n"
        resp = _upload_csv(client, csv)
        assert resp.status_code == 201
        assert resp.get_json()["imported"] == 1

    def test_csv_with_invalid_email_skips_row(self, client):
        """A row with an invalid email format should be skipped."""
        csv = "username,email\nbademail_user,notanemail\n"
        resp = _upload_csv(client, csv)
        assert resp.status_code == 201
        assert resp.get_json()["imported"] == 0

    def test_csv_with_no_at_sign_email_skips_row(self, client):
        """An email missing @ sign should be skipped during bulk upload."""
        csv = "username,email\nnoatuser,justastring\n"
        resp = _upload_csv(client, csv)
        assert resp.status_code == 201
        assert resp.get_json()["imported"] == 0

    def test_csv_with_no_domain_dot_email_skips_row(self, client):
        """An email with no dot in the domain should be skipped."""
        csv = "username,email\nnodotuser,user@nodot\n"
        resp = _upload_csv(client, csv)
        assert resp.status_code == 201
        assert resp.get_json()["imported"] == 0


# ---------------------------------------------------------------------------
# 2. URL Creation Edge Cases — Data Type Validation
# ---------------------------------------------------------------------------

class TestUrlCreationDataTypes:
    def test_reject_integer_username_in_user_creation(self, client):
        """The spec says: reject invalid data schemas e.g. integer for username."""
        resp = client.post(
            "/users", json={"username": 12345, "email": "intuser@example.com"}
        )
        assert resp.status_code == 400

    def test_reject_boolean_email_in_user_creation(self, client):
        """Boolean for email field must be rejected."""
        resp = client.post(
            "/users", json={"username": "booluser", "email": True}
        )
        assert resp.status_code == 400

    def test_reject_list_username_in_user_creation(self, client):
        """A list for username must be rejected."""
        resp = client.post(
            "/users", json={"username": ["a", "b"], "email": "list@example.com"}
        )
        assert resp.status_code == 400

    def test_reject_none_username_in_user_creation(self, client):
        """Null/None for username must be rejected."""
        resp = client.post(
            "/users", json={"username": None, "email": "null@example.com"}
        )
        assert resp.status_code == 400

    def test_reject_integer_url_field(self, client):
        """Integer for the url field must be rejected."""
        resp = client.post("/urls", json={"url": 12345})
        assert resp.status_code == 400

    def test_reject_boolean_url_field(self, client):
        """Boolean for the url field must be rejected."""
        resp = client.post("/urls", json={"url": True})
        assert resp.status_code == 400

    def test_reject_null_url_field(self, client):
        """Null for the url field must be rejected."""
        resp = client.post("/urls", json={"url": None})
        assert resp.status_code == 400

    def test_create_url_with_empty_title(self, client):
        """Empty string title should be stored as None (stripped away)."""
        resp = _create_url(client, url="https://empty-title.example.com", title="")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] is None

    def test_create_url_with_whitespace_title(self, client):
        """Whitespace-only title should be stored as None."""
        resp = _create_url(
            client, url="https://ws-title.example.com", title="   "
        )
        assert resp.status_code == 201
        assert resp.get_json()["title"] is None

    def test_create_url_with_very_long_url(self, client):
        """A valid but very long URL should still be accepted."""
        long_path = "a" * 2000
        long_url = f"https://example.com/{long_path}"
        resp = _create_url(client, url=long_url)
        assert resp.status_code == 201
        assert resp.get_json()["original_url"] == long_url

    def test_create_url_with_query_params(self, client):
        """URLs with query parameters should be preserved exactly."""
        url_with_params = "https://example.com/search?q=hello&page=1&sort=desc"
        resp = _create_url(client, url=url_with_params)
        assert resp.status_code == 201
        assert resp.get_json()["original_url"] == url_with_params

    def test_create_url_with_fragment(self, client):
        """URLs with fragments should be accepted."""
        url_with_fragment = "https://example.com/docs#section-3"
        resp = _create_url(client, url=url_with_fragment)
        assert resp.status_code == 201
        assert resp.get_json()["original_url"] == url_with_fragment


# ---------------------------------------------------------------------------
# 3. Update Edge Cases
# ---------------------------------------------------------------------------

class TestUpdateEdgeCases:
    def test_update_nonexistent_user_returns_404(self, client):
        resp = client.put("/users/99999", json={"username": "ghost"})
        assert resp.status_code == 404

    def test_update_user_with_empty_body(self, client):
        """PUT with empty JSON object should succeed (no-op update)."""
        create_resp = _create_user(client, "emptyupd", "emptyupd@example.com")
        user_id = create_resp.get_json()["id"]
        resp = client.put(f"/users/{user_id}", json={})
        assert resp.status_code == 200
        assert resp.get_json()["username"] == "emptyupd"

    def test_partial_update_user_keeps_other_fields(self, client):
        """Updating only username should preserve the email."""
        create_resp = _create_user(client, "partialuser", "partial@example.com")
        user_id = create_resp.get_json()["id"]
        resp = client.put(f"/users/{user_id}", json={"username": "updated_partial"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["username"] == "updated_partial"
        assert data["email"] == "partial@example.com"

    def test_partial_update_url_keeps_other_fields(self, client):
        """Updating only the title should preserve the original URL."""
        create_resp = _create_url(
            client, url="https://partial-url.example.com", title="Original"
        )
        url_id = create_resp.get_json()["id"]
        resp = client.put(f"/urls/{url_id}", json={"title": "Updated Title"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["title"] == "Updated Title"
        assert data["original_url"] == "https://partial-url.example.com"

    def test_update_url_with_empty_body(self, client):
        """PUT /urls/:id with empty JSON object should succeed (no-op)."""
        create_resp = _create_url(client, url="https://noop-url.example.com")
        url_id = create_resp.get_json()["id"]
        resp = client.put(f"/urls/{url_id}", json={})
        assert resp.status_code == 200

    def test_update_user_integer_username_rejected(self, client):
        """Updating username to an integer must be rejected."""
        create_resp = _create_user(client, "intupd", "intupd@example.com")
        user_id = create_resp.get_json()["id"]
        resp = client.put(f"/users/{user_id}", json={"username": 42})
        assert resp.status_code == 400

    def test_update_user_integer_email_rejected(self, client):
        """Updating email to an integer must be rejected."""
        create_resp = _create_user(client, "intemailupd", "intemail@example.com")
        user_id = create_resp.get_json()["id"]
        resp = client.put(f"/users/{user_id}", json={"email": 42})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Redirect Edge Cases
# ---------------------------------------------------------------------------

class TestRedirectEdgeCases:
    def test_redirect_preserves_query_params_in_original(self, client):
        """When the original URL has query params, the redirect Location must include them."""
        original = "https://example.com/search?q=test&page=2"
        create_resp = _create_url(client, url=original)
        short_code = create_resp.get_json()["short_code"]

        resp = client.get(f"/{short_code}")
        assert resp.status_code == 302
        assert resp.headers["Location"] == original

    def test_redirect_for_just_deleted_url_returns_404(self, client):
        """A URL that was just soft-deleted must immediately return 404."""
        create_resp = _create_url(client, url="https://just-deleted.example.com")
        url_id = create_resp.get_json()["id"]
        short_code = create_resp.get_json()["short_code"]

        # Delete it
        client.delete(f"/urls/{url_id}")

        # Redirect should fail
        resp = client.get(f"/{short_code}")
        assert resp.status_code == 404

        # No redirect event should exist
        redirect_events = list(
            Event.select().where(
                (Event.url_id == url_id) & (Event.event_type == "redirect")
            )
        )
        assert len(redirect_events) == 0

    def test_redirect_for_reactivated_url_works(self, client):
        """A URL that was deleted and then reactivated should redirect again."""
        create_resp = _create_url(client, url="https://reactivated.example.com")
        url_id = create_resp.get_json()["id"]
        short_code = create_resp.get_json()["short_code"]

        # Delete
        client.delete(f"/urls/{url_id}")
        assert client.get(f"/{short_code}").status_code == 404

        # Reactivate
        client.put(f"/urls/{url_id}", json={"is_active": True})

        # Should work again
        resp = client.get(f"/{short_code}")
        assert resp.status_code == 302
        assert "reactivated.example.com" in resp.headers["Location"]

    def test_redirect_with_encoded_characters_in_url(self, client):
        """URLs with encoded characters should be preserved in the redirect."""
        original = "https://example.com/path%20with%20spaces?q=hello%20world"
        create_resp = _create_url(client, url=original)
        short_code = create_resp.get_json()["short_code"]

        resp = client.get(f"/{short_code}")
        assert resp.status_code == 302
        assert resp.headers["Location"] == original


# ---------------------------------------------------------------------------
# 5. Additional Contract Tests
# ---------------------------------------------------------------------------

class TestMiscContractEdgeCases:
    def test_delete_user_is_hard_delete(self, client):
        """User delete is a hard delete (not soft-delete like URLs)."""
        create_resp = _create_user(client, "harddelete", "harddelete@example.com")
        user_id = create_resp.get_json()["id"]
        client.delete(f"/users/{user_id}")
        resp = client.get(f"/users/{user_id}")
        assert resp.status_code == 404

    def test_url_delete_is_soft_delete(self, client):
        """URL delete is a soft delete; the record still exists."""
        create_resp = _create_url(client, url="https://soft-del-proof.example.com")
        url_id = create_resp.get_json()["id"]
        client.delete(f"/urls/{url_id}")
        resp = client.get(f"/urls/{url_id}")
        assert resp.status_code == 200
        assert resp.get_json()["is_active"] is False

    def test_double_delete_url_returns_204_then_404(self, client):
        """Deleting an already-deleted URL should return 404."""
        create_resp = _create_url(client, url="https://double-del.example.com")
        url_id = create_resp.get_json()["id"]
        resp1 = client.delete(f"/urls/{url_id}")
        assert resp1.status_code == 204
        resp2 = client.delete(f"/urls/{url_id}")
        assert resp2.status_code == 404

    def test_list_urls_pagination(self, client):
        """Pagination parameters should limit results."""
        for i in range(5):
            _create_url(client, url=f"https://paginate{i}.example.com")
        resp = client.get("/urls?page=1&per_page=2")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_list_urls_filter_by_user_id(self, client):
        """Filtering URLs by user_id should only return that user's URLs."""
        user_resp = _create_user(client, "filteruser", "filter@example.com")
        user_id = user_resp.get_json()["id"]
        _create_url(client, url="https://owned.example.com", user_id=user_id)
        _create_url(client, url="https://unowned.example.com")

        resp = client.get(f"/urls?user_id={user_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["user_id"] == user_id

    def test_create_url_with_user_id_zero_rejected(self, client):
        """user_id=0 should be rejected as invalid."""
        resp = client.post(
            "/urls",
            json={"url": "https://zero-user.example.com", "user_id": 0},
        )
        assert resp.status_code == 400

    def test_url_stats_includes_url_data(self, client):
        """Stats endpoint should include the URL metadata alongside the count."""
        create_resp = _create_url(client, url="https://stats-meta.example.com")
        url_id = create_resp.get_json()["id"]
        resp = client.get(f"/urls/{url_id}/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "url" in data
        assert data["url"]["original_url"] == "https://stats-meta.example.com"
        assert "redirect_count" in data
