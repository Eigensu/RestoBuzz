"""Campaign audience row classification.

Extracted from a closure inside members_as_contacts; these rules previously
had no direct test even though they decide who receives a campaign.
"""

from app.routers.members import _ContactCollector


class TestValidRows:
    def test_a_normal_row_becomes_a_contact(self):
        c = _ContactCollector(set())
        c.add("Asha", "9324081080")
        assert len(c.valid_rows) == 1
        assert c.valid_rows[0].phone == "+919324081080"
        assert c.valid_rows[0].name == "Asha"

    def test_a_missing_name_is_allowed(self):
        c = _ContactCollector(set())
        c.add("", "9324081080")
        assert c.valid_rows[0].name == ""

    def test_excel_float_artifact_is_handled(self):
        c = _ContactCollector(set())
        c.add("Asha", "919324081080.0")
        assert c.valid_rows[0].phone == "+919324081080"


class TestRejections:
    def test_empty_phone_is_reported_not_dropped(self):
        c = _ContactCollector(set())
        c.add("Asha", "")
        assert not c.valid_rows
        assert c.invalid_rows[0].reason == "Empty phone"

    def test_none_phone_is_reported(self):
        c = _ContactCollector(set())
        c.add("Asha", None)
        assert c.invalid_rows[0].reason == "Empty phone"

    def test_unparseable_phone_is_reported_with_its_raw_value(self):
        c = _ContactCollector(set())
        c.add("Asha", "not-a-number")
        assert c.invalid_rows[0].reason == "Invalid phone number"
        assert c.invalid_rows[0].raw_value == "not-a-number"

    def test_row_numbers_count_every_row(self):
        c = _ContactCollector(set())
        c.add("A", "9324081080")   # row 1, valid
        c.add("B", "")             # row 2, invalid
        assert c.invalid_rows[0].row_number == 2


class TestDeduplication:
    def test_repeat_of_the_same_number_is_a_duplicate(self):
        c = _ContactCollector(set())
        c.add("Asha", "9324081080")
        c.add("Asha again", "9324081080")
        assert len(c.valid_rows) == 1
        assert c.duplicate_count == 1

    def test_different_formats_of_one_number_collapse(self):
        """+91 prefixed and bare forms must not both receive the campaign."""
        c = _ContactCollector(set())
        c.add("Asha", "9324081080")
        c.add("Asha", "+919324081080")
        assert len(c.valid_rows) == 1
        assert c.duplicate_count == 1


class TestSuppression:
    def test_a_suppressed_number_never_becomes_a_contact(self):
        c = _ContactCollector({"+919324081080"})
        c.add("Asha", "9324081080")
        assert not c.valid_rows
        assert c.suppressed_count == 1

    def test_suppression_is_checked_after_normalisation(self):
        """A suppressed number must stay suppressed in any input format."""
        c = _ContactCollector({"+919324081080"})
        c.add("Asha", "919324081080.0")
        assert not c.valid_rows
        assert c.suppressed_count == 1

    def test_a_duplicate_of_a_suppressed_number_is_not_double_counted(self):
        c = _ContactCollector({"+919324081080"})
        c.add("Asha", "9324081080")
        c.add("Asha", "9324081080")
        assert c.suppressed_count == 1
        assert c.duplicate_count == 1


class TestPreflight:
    def test_counts_are_reported_together(self):
        c = _ContactCollector({"+919000000001"})
        c.add("ok", "9324081080")
        c.add("dupe", "9324081080")
        c.add("bad", "nope")
        c.add("suppressed", "9000000001")

        result = c.to_preflight("ref-123")
        assert result.valid_count == 1
        assert result.duplicate_count == 1
        assert result.invalid_count == 1
        assert result.suppressed_count == 1
        assert result.file_ref == "ref-123"
