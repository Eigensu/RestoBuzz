"""Excel float artifacts in phone cells.

openpyxl returns a long numeric cell as a float, so "919324081080" arrives as
919324081080.0. Rendering that with str() gives "919324081080.0"; stripping
non-digits without dropping the ".0" first yields "9193240810800", and the last
ten digits of that are a DIFFERENT phone number. The guest parser guarded
against this; the bill parser did not, so every bill row in production is
stored with the suffix.
"""

import pytest

from app.routers.reservego import _phone_str
from app.services.dormancy_service import normalize_phone_for_match


class TestPhoneStr:
    def test_float_cell_loses_the_artifact(self):
        assert _phone_str(919324081080.0) == "919324081080"

    def test_string_with_suffix_is_cleaned(self):
        assert _phone_str("919324081080.0") == "919324081080"

    def test_clean_string_is_untouched(self):
        assert _phone_str("919324081080") == "919324081080"

    def test_whitespace_is_trimmed(self):
        assert _phone_str("  919324081080  ") == "919324081080"

    def test_empty_and_none_become_none(self):
        assert _phone_str(None) is None
        assert _phone_str("") is None
        assert _phone_str("   ") is None

    def test_non_integral_float_is_not_mangled_into_a_number(self):
        # Not a phone number; keep it visible rather than silently truncating.
        assert _phone_str(12.5) == "12.5"


class TestNormalizeForMatch:
    def test_float_artifact_and_clean_form_agree(self):
        """The regression: these two must produce the same key."""
        assert (
            normalize_phone_for_match("919324081080.0")
            == normalize_phone_for_match("919324081080")
            == "9324081080"
        )

    def test_the_artifact_used_to_shift_the_digits(self):
        """Guard the specific corruption: never the naive last-10 of the
        digits of "919324081080.0", which is "3240810800"."""
        assert normalize_phone_for_match("919324081080.0") != "3240810800"

    @pytest.mark.parametrize(
        "raw",
        ["+91 93240 81080", "91-9324081080", "9324081080", "919324081080"],
    )
    def test_formatting_variants_collapse_to_one_key(self, raw):
        assert normalize_phone_for_match(raw) == "9324081080"

    def test_short_fragments_are_rejected(self):
        # A 9-digit typo must not match anyone by suffix.
        assert normalize_phone_for_match("8335 22529") is None

    def test_empty_inputs(self):
        assert normalize_phone_for_match(None) is None
        assert normalize_phone_for_match("") is None
