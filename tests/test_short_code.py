"""Tests for app.utils.short_code."""

import string

from app.utils.short_code import generate_short_code

ALPHANUMERIC = set(string.ascii_letters + string.digits)


def test_default_length():
    code = generate_short_code()
    assert len(code) == 6


def test_custom_length():
    code = generate_short_code(length=10)
    assert len(code) == 10


def test_only_alphanumeric():
    for _ in range(50):
        code = generate_short_code()
        assert all(c in ALPHANUMERIC for c in code)


def test_different_codes_on_each_call():
    codes = {generate_short_code() for _ in range(20)}
    # With 62^6 possibilities, 20 calls should give 20 distinct codes.
    assert len(codes) == 20


def test_length_one():
    code = generate_short_code(length=1)
    assert len(code) == 1
    assert code in ALPHANUMERIC
