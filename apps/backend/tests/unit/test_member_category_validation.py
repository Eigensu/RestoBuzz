"""Category validation must agree with category filtering.

Categories are stored lowercased and matched case-insensitively when
filtering, so validation that compares exact strings would reject "NFC" on
create/import while `?category=NFC` matches those very rows.
"""

import pytest

from app.core.errors import ValidationError
from app.routers.members import _resolve_category
from app.services import member_segments as ms


def _restaurant(categories):
    return {"id": "r1", "member_categories": categories}


class TestResolveCategory:
    def test_exact_match_returns_stored_form(self):
        assert _resolve_category(_restaurant(["nfc", "ecard"]), "nfc") == "nfc"

    @pytest.mark.parametrize("raw", ["NFC", "Nfc", "nFc", "  nfc  "])
    def test_casing_and_whitespace_are_accepted(self, raw):
        assert _resolve_category(_restaurant(["nfc", "ecard"]), raw) == "nfc"

    def test_custom_categories_work_the_same(self):
        assert _resolve_category(_restaurant(["visitors"]), "VISITORS") == "visitors"

    def test_returns_the_stored_spelling_not_the_input(self):
        """What gets written must match what the filter searches for."""
        stored = _resolve_category(_restaurant(["nfc"]), "NFC")
        clause = ms.category_clause(stored)
        assert clause["type"]["$regex"] == "^nfc$"

    def test_unknown_category_is_rejected(self):
        restaurant = _restaurant(["nfc", "ecard"])
        with pytest.raises(ValidationError):
            _resolve_category(restaurant, "vip")

    def test_segment_name_is_rejected_as_a_category(self):
        restaurant = _restaurant(["nfc", "ecard"])
        with pytest.raises(ValidationError):
            _resolve_category(restaurant, "interested")

    def test_missing_config_falls_back_to_defaults(self):
        assert _resolve_category({"id": "r1"}, "ecard") == "ecard"
        assert _resolve_category({"id": "r1", "member_categories": []}, "nfc") == "nfc"

    def test_empty_input_is_rejected(self):
        restaurant = _restaurant(["nfc"])
        with pytest.raises(ValidationError):
            _resolve_category(restaurant, "")
