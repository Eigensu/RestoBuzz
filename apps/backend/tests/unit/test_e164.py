import pytest
from app.services.contact_parser import _normalize_phone


def test_valid_us_number():
    assert _normalize_phone("+12125551234") == "+12125551234"


def test_local_us_number_with_region():
    assert _normalize_phone("2125551234", "US") == "+12125551234"


def test_international_uk():
    assert _normalize_phone("+447911123456") == "+447911123456"


def test_invalid_number_returns_none():
    assert _normalize_phone("not-a-phone") is None


def test_too_short_returns_none():
    assert _normalize_phone("123") is None


def test_empty_returns_none():
    assert _normalize_phone("") is None


def test_with_formatting():
    assert _normalize_phone("+1 (212) 555-1234") == "+12125551234"
