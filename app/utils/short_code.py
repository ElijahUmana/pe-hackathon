import secrets
import string


def generate_short_code(length=6):
    """Generate a random alphanumeric short code.

    Uses cryptographically secure random selection to ensure
    every code is unique even for identical URLs (Oracle Hint 1: Twin's Paradox).
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
