"""Tests for the category/segment split.

The bug these lock down: category filtering used to be an allowlist of
["nfc", "ecard"], so any admin-configured category matched no branch, added no
clause, and silently returned every member in the restaurant.
"""

import pytest

from app.services import member_segments as ms


class TestResolveAxes:
    def test_custom_category_lands_on_the_category_axis(self):
        assert ms.resolve_axes(None, None, "vip") == ("vip", None)

    def test_builtin_categories_still_work(self):
        assert ms.resolve_axes(None, None, "nfc") == ("nfc", None)
        assert ms.resolve_axes(None, None, "ecard") == ("ecard", None)

    def test_segment_names_land_on_the_segment_axis(self):
        assert ms.resolve_axes(None, None, "inactive") == (None, "inactive")
        assert ms.resolve_axes(None, None, "interested") == (None, "interested")

    def test_all_and_none_constrain_neither_axis(self):
        assert ms.resolve_axes(None, None, "all") == (None, None)
        assert ms.resolve_axes(None, None, None) == (None, None)
        assert ms.resolve_axes("all", "all", None) == (None, None)

    def test_axes_compose(self):
        assert ms.resolve_axes("vip", "inactive", None) == ("vip", "inactive")

    def test_segment_sent_as_category_is_rerouted(self):
        """An old client sending ?category=dormant must not filter on type."""
        assert ms.resolve_axes("dormant", None, None) == (None, "dormant")

    def test_explicit_axes_win_over_legacy_type(self):
        assert ms.resolve_axes("vip", None, "nfc") == ("vip", None)

    def test_values_are_normalised(self):
        assert ms.resolve_axes("  VIP  ", None, None) == ("vip", None)


class TestCategoryClause:
    def test_custom_category_produces_a_real_filter(self):
        """The regression: this used to return {} and match everyone."""
        clause = ms.category_clause("vip")
        assert clause["type"]["$regex"] == "^vip$"
        assert clause["type"]["$options"] == "i"

    def test_no_category_means_no_constraint(self):
        assert ms.category_clause(None) == {}

    def test_regex_metacharacters_are_escaped(self):
        assert ms.category_clause("a.b")["type"]["$regex"] == r"^a\.b$"


class TestSegmentClause:
    def test_interested_filters_on_the_tag_not_the_type(self):
        assert ms.segment_clause("interested") == {"tags": "interested"}

    def test_inactive_spans_the_three_lapsed_tiers(self):
        assert ms.segment_clause("inactive") == {
            "dormancy_tier": {"$in": ["AT_RISK", "DORMANT", "LOST"]}
        }

    @pytest.mark.parametrize(
        "segment,tier",
        [("active", "ACTIVE"), ("at_risk", "AT_RISK"),
         ("dormant", "DORMANT"), ("lost", "LOST")],
    )
    def test_each_tier_maps_to_its_stored_value(self, segment, tier):
        assert ms.segment_clause(segment) == {"dormancy_tier": tier}

    def test_unknown_segment_does_not_invent_a_filter(self):
        assert ms.segment_clause("nonsense") == {}
        assert ms.segment_clause(None) == {}


class TestBuildMemberQuery:
    def test_both_axes_compose_into_one_query(self):
        q = ms.build_member_query({"restaurant_id": "r1"}, "vip", "inactive")
        assert q["restaurant_id"] == "r1"
        assert q["type"]["$regex"] == "^vip$"
        assert q["dormancy_tier"] == {"$in": ["AT_RISK", "DORMANT", "LOST"]}

    def test_base_filter_is_preserved(self):
        q = ms.build_member_query({"restaurant_id": "r1", "is_active": True}, None, None)
        assert q == {"restaurant_id": "r1", "is_active": True}


class _Row:
    def __init__(self, type=None, dormancy_tier=None, tags=None):
        self.type = type
        self.dormancy_tier = dormancy_tier
        self.tags = tags or []


class TestInMemoryPredicates:
    """The r2 path merges two sources and filters in memory — it must agree
    with the Mongo clauses above, or the same tab means different things on
    different restaurants."""

    def test_category_predicate_is_case_insensitive(self):
        assert ms.matches_category(_Row(type="VIP"), "vip")
        assert not ms.matches_category(_Row(type="nfc"), "vip")

    def test_no_category_matches_everything(self):
        assert ms.matches_category(_Row(type="anything"), None)

    def test_inactive_predicate_matches_the_clause(self):
        assert ms.matches_segment(_Row(dormancy_tier="LOST"), "inactive")
        assert ms.matches_segment(_Row(dormancy_tier="AT_RISK"), "inactive")
        assert not ms.matches_segment(_Row(dormancy_tier="ACTIVE"), "inactive")
        assert not ms.matches_segment(_Row(dormancy_tier="UNKNOWN"), "inactive")

    def test_dormant_means_the_tier_not_a_30_day_cutoff(self):
        """r2 used to define dormant as last_visit < 30d — a different
        population from every other restaurant's DORMANT tier."""
        assert ms.matches_segment(_Row(dormancy_tier="DORMANT"), "dormant")
        assert not ms.matches_segment(_Row(dormancy_tier="AT_RISK"), "dormant")

    def test_interested_predicate_reads_tags(self):
        assert ms.matches_segment(_Row(tags=["interested"]), "interested")
        assert not ms.matches_segment(_Row(tags=[]), "interested")

    def test_no_segment_matches_everything(self):
        assert ms.matches_segment(_Row(), None)


class TestReservedNames:
    def test_every_segment_is_reserved(self):
        assert ms.SEGMENT_IDS <= ms.RESERVED_CATEGORY_NAMES

    def test_wire_sentinels_are_reserved(self):
        assert "all" in ms.RESERVED_CATEGORY_NAMES
        assert "reservego" in ms.RESERVED_CATEGORY_NAMES

    def test_ordinary_names_are_not_reserved(self):
        assert "vip" not in ms.RESERVED_CATEGORY_NAMES
        assert "nfc" not in ms.RESERVED_CATEGORY_NAMES


class TestFieliaRouting:
    """Fielia holds NFC cards only and is strictly read-only."""

    def test_unconstrained_and_nfc_listings_include_fielia(self):
        assert ms.fielia_supplies(None)
        assert ms.fielia_supplies("nfc")
        assert ms.fielia_supplies("NFC")

    def test_other_categories_cannot_match_a_fielia_card(self):
        assert not ms.fielia_supplies("ecard")
        assert not ms.fielia_supplies("vip")
