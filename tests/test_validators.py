"""Tests for app.utils.validators."""

from app.utils.validators import is_valid_url, validate_email

# ---------------------------------------------------------------------------
# is_valid_url
# ---------------------------------------------------------------------------

class TestIsValidUrl:
    def test_http_url(self):
        assert is_valid_url("http://example.com") is True

    def test_https_url(self):
        assert is_valid_url("https://example.com") is True

    def test_https_with_path(self):
        assert is_valid_url("https://example.com/path/to/page") is True

    def test_https_with_query(self):
        assert is_valid_url("https://example.com?q=1&r=2") is True

    def test_https_with_port(self):
        assert is_valid_url("https://example.com:8080/api") is True

    def test_no_scheme(self):
        assert is_valid_url("example.com") is False

    def test_ftp_scheme(self):
        assert is_valid_url("ftp://files.example.com") is False

    def test_single_word(self):
        assert is_valid_url("hello") is False

    def test_empty_string(self):
        assert is_valid_url("") is False

    def test_none(self):
        assert is_valid_url(None) is False

    def test_whitespace_only(self):
        assert is_valid_url("   ") is False

    def test_integer_input(self):
        assert is_valid_url(42) is False

    def test_missing_netloc(self):
        assert is_valid_url("http://") is False

    def test_scheme_only(self):
        assert is_valid_url("https://") is False

    def test_javascript_scheme(self):
        assert is_valid_url("javascript:alert(1)") is False


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------

class TestValidateEmail:
    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_valid_email_subdomain(self):
        assert validate_email("user@mail.example.com") is True

    def test_missing_at(self):
        assert validate_email("userexample.com") is False

    def test_missing_domain(self):
        assert validate_email("user@") is False

    def test_missing_local(self):
        assert validate_email("@example.com") is False

    def test_no_dot_in_domain(self):
        assert validate_email("user@localhost") is False

    def test_empty_string(self):
        assert validate_email("") is False

    def test_none(self):
        assert validate_email(None) is False

    def test_whitespace(self):
        assert validate_email("   ") is False

    def test_multiple_at(self):
        assert validate_email("a@b@c.com") is False

    def test_integer(self):
        assert validate_email(123) is False
