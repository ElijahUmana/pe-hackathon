from urllib.parse import urlparse


def is_valid_url(url_string):
    """Validate that a string is a well-formed HTTP/HTTPS URL.

    Oracle Hint 5 (Deceitful Scroll): reject single words, missing schemes,
    non-http(s) schemes, and other malformed URLs.
    """
    if not url_string or not isinstance(url_string, str):
        return False
    url_string = url_string.strip()
    if not url_string:
        return False
    try:
        result = urlparse(url_string)
        return all([
            result.scheme in ("http", "https"),
            result.netloc,
            len(result.netloc) > 1,
        ])
    except Exception:
        return False


def validate_email(email):
    """Basic email format validation."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if not email:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain:
        return False
    if "." not in domain:
        return False
    return True
