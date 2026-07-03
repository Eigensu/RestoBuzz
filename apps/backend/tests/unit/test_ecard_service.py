import cloudinary
import pytest

from app.services.ecard_service import build_card_url, sample_card_url

# The SDK needs a cloud_name to build URLs; env may not set one under test.
cloudinary.config(cloud_name="test_cloud", secure=True)

BASE = "whatsapp-media/fielia_card"


def test_url_contains_cloud_and_base():
    url = build_card_url(BASE, "Aarav Mehta")
    assert url.startswith("https://res.cloudinary.com/test_cloud/")
    assert BASE in url


def test_text_overlay_present_and_spaces_encoded():
    url = build_card_url(BASE, "Aarav Mehta")
    assert "l_text:" in url
    # Space is encoded, never a literal space in the URL.
    assert " " not in url
    assert "Aarav%20Mehta" in url


def test_comma_in_name_is_double_escaped():
    # Cloudinary text layers treat ',' as a delimiter — it must be escaped so it
    # doesn't split the transformation. Bare '%2C' would break; SDK double-escapes.
    url = build_card_url(BASE, "Doe, Jane")
    assert "l_text:" in url
    assert "%252C" in url  # double-encoded comma


def test_emoji_name_does_not_crash_and_encodes():
    url = build_card_url(BASE, "Priya 🎉")
    assert "l_text:" in url
    assert " " not in url


def test_overlay_overrides_applied():
    url = build_card_url(
        BASE,
        "Sam",
        overlay={"color": "000000", "font_size": 80, "y": 120, "gravity": "south"},
    )
    assert "co_rgb:000000" in url
    assert "_80_" in url  # font_size in l_text:<font>_<size>_<weight>
    assert "y_120" in url
    assert "g_south" in url


def test_color_leading_hash_is_stripped():
    url = build_card_url(BASE, "Sam", overlay={"color": "#ff0000"})
    assert "co_rgb:ff0000" in url
    assert "co_rgb:%23" not in url  # no encoded '#'


def test_long_name_truncated():
    long_name = "A" * 100
    url = build_card_url(BASE, long_name)
    assert "A" * 100 not in url  # truncated to _MAX_NAME_LEN


def test_blank_name_returns_base_without_overlay():
    url = build_card_url(BASE, "   ")
    assert "l_text:" not in url
    assert BASE in url


def test_output_is_jpg_quality_auto():
    url = build_card_url(BASE, "Sam")
    assert "f_jpg" in url
    assert "q_auto" in url


def test_distinct_names_yield_distinct_urls():
    a = build_card_url(BASE, "Aarav")
    b = build_card_url(BASE, "Priya")
    assert a != b


def test_sample_card_url_has_placeholder_name():
    url = sample_card_url(BASE)
    assert "l_text:" in url
    assert "Aarav" in url
