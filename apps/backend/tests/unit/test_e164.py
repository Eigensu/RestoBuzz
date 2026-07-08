import pytest
from app.utils.phone import normalize_phone as _normalize_phone


def test_valid_us_number():
    assert _normalize_phone("+12125551234") == "+12125551234"


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


# ── India default-region behavior (the bulk-import fix) ────────────────────────


def test_bare_ten_digit_indian_gets_country_code():
    # The core bug: a 10-digit sheet number must become +91..., not +7977539750.
    assert _normalize_phone("7977539750") == "+917977539750"


def test_indian_number_with_country_code_no_plus():
    assert _normalize_phone("917977539750") == "+917977539750"


def test_indian_number_with_plus_kept():
    assert _normalize_phone("+917977539750") == "+917977539750"


def test_indian_leading_zero_national_prefix():
    assert _normalize_phone("07977539750") == "+917977539750"


def test_indian_with_spaces_from_excel():
    assert _normalize_phone(" +91 79775 39750 ") == "+917977539750"


def test_excel_float_artifact_stripped():
    assert _normalize_phone("7977539750.0") == "+917977539750"


def test_eleven_digit_indian_is_invalid():
    # One extra digit is not a valid Indian number — surfaced as invalid.
    assert _normalize_phone("79775397500") is None


def test_international_number_not_forced_to_india():
    # A real US number must stay US even though the default region is IN.
    assert _normalize_phone("+14155552671") == "+14155552671"


def test_region_override():
    assert _normalize_phone("2125551234", region="US") == "+12125551234"
