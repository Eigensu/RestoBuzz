"""Rules for the BUTTONS component of a WhatsApp template.

Meta answers a malformed button set with a generic "invalid parameter" that
names neither the rule nor the row, so the router checks every rule itself.
These tests pin the checks and, just as importantly, the two shapes Meta is
strict about: quick replies grouped together, and BUTTONS last.
"""

import pytest

from app.core.errors import ValidationError
from app.routers.templates import (
    MAX_BUTTONS,
    TemplateButton,
    TemplateComponent,
    _normalize_buttons,
    _normalize_component_for_meta,
    _order_components,
)


def _btn(**kwargs) -> TemplateButton:
    return TemplateButton(**kwargs)


def _quick(text: str) -> TemplateButton:
    return _btn(type="QUICK_REPLY", text=text)


# ── Shapes Meta accepts ───────────────────────────────────────────────────────


def test_each_button_type_reduces_to_its_meta_shape():
    result = _normalize_buttons(
        [
            _btn(type="URL", text="View menu", url="https://dishpatch.in/menu"),
            _btn(type="PHONE_NUMBER", text="Call now", phone_number="+919876543210"),
            _btn(type="COPY_CODE", example="FEAST20"),
            _quick("Book a table"),
        ]
    )

    assert result == [
        {"type": "URL", "text": "View menu", "url": "https://dishpatch.in/menu"},
        {
            "type": "PHONE_NUMBER",
            "text": "Call now",
            "phone_number": "+919876543210",
        },
        {"type": "COPY_CODE", "example": "FEAST20"},
        {"type": "QUICK_REPLY", "text": "Book a table"},
    ]


def test_quick_replies_are_grouped_after_call_to_action_buttons():
    """Meta rejects a mixed set whose quick replies are interleaved."""
    result = _normalize_buttons(
        [
            _quick("Yes"),
            _btn(type="URL", text="View menu", url="https://dishpatch.in/menu"),
            _quick("No"),
        ]
    )

    assert [b["type"] for b in result] == ["URL", "QUICK_REPLY", "QUICK_REPLY"]
    assert [b["text"] for b in result] == ["View menu", "Yes", "No"]


def test_phone_number_is_stored_in_e164():
    (button,) = _normalize_buttons(
        [_btn(type="PHONE_NUMBER", text="Call now", phone_number="98765 43210")]
    )
    assert button["phone_number"] == "+919876543210"


def test_whitespace_around_values_is_trimmed():
    result = _normalize_buttons(
        [
            _btn(type="URL", text="  View menu  ", url="  https://a.test/m  "),
            _btn(type="COPY_CODE", example="  FEAST20  "),
        ]
    )
    assert result[0] == {"type": "URL", "text": "View menu", "url": "https://a.test/m"}
    assert result[1] == {"type": "COPY_CODE", "example": "FEAST20"}


# ── Caps ──────────────────────────────────────────────────────────────────────


def test_more_than_ten_buttons_is_rejected():
    with pytest.raises(ValidationError, match="at most 10 buttons"):
        _normalize_buttons([_quick(f"Reply {i}") for i in range(MAX_BUTTONS + 1)])


def test_a_third_url_button_is_rejected():
    with pytest.raises(ValidationError, match="At most 2 URL"):
        _normalize_buttons(
            [
                _btn(type="URL", text=f"Link {i}", url=f"https://a.test/{i}")
                for i in range(3)
            ]
        )


@pytest.mark.parametrize("btn_type", ["PHONE_NUMBER", "COPY_CODE"])
def test_only_one_phone_or_copy_code_button(btn_type):
    button = (
        _btn(type="PHONE_NUMBER", text="Call", phone_number="+919876543210")
        if btn_type == "PHONE_NUMBER"
        else _btn(type="COPY_CODE", example="FEAST20")
    )
    with pytest.raises(ValidationError, match="At most 1"):
        _normalize_buttons([button, button.model_copy()])


# ── Per-button rules ──────────────────────────────────────────────────────────


def test_empty_button_set_is_rejected():
    with pytest.raises(ValidationError, match="requires structured buttons"):
        _normalize_buttons([])


def test_unsupported_button_type_names_what_is_supported():
    with pytest.raises(ValidationError, match="Unsupported button type 'FLOW'"):
        _normalize_buttons([_btn(type="FLOW", text="Open")])


def test_button_text_is_required():
    with pytest.raises(ValidationError, match="needs button text"):
        _normalize_buttons([_quick("   ")])


def test_button_text_over_twenty_five_characters_is_rejected():
    with pytest.raises(ValidationError, match="exceeds 25 characters"):
        _normalize_buttons([_quick("x" * 26)])


def test_duplicate_button_text_is_rejected():
    with pytest.raises(ValidationError, match="Duplicate button text"):
        _normalize_buttons([_quick("Yes"), _quick("yes")])


def test_url_must_carry_a_scheme():
    with pytest.raises(ValidationError, match="must start with https"):
        _normalize_buttons([_btn(type="URL", text="Menu", url="dishpatch.in/menu")])


def test_dynamic_url_is_rejected_until_send_time_parameters_exist():
    """_build_payload emits no button parameters, so {{1}} would ship verbatim."""
    with pytest.raises(ValidationError, match="variable in its URL"):
        _normalize_buttons(
            [_btn(type="URL", text="Menu", url="https://a.test/{{1}}")]
        )


def test_unparseable_phone_number_is_rejected():
    with pytest.raises(ValidationError, match="valid phone number"):
        _normalize_buttons([_btn(type="PHONE_NUMBER", text="Call", phone_number="123")])


def test_copy_code_requires_an_offer_code():
    with pytest.raises(ValidationError, match="needs an offer code"):
        _normalize_buttons([_btn(type="COPY_CODE", example="  ")])


def test_offer_code_over_fifteen_characters_is_rejected():
    with pytest.raises(ValidationError, match="15 characters or fewer"):
        _normalize_buttons([_btn(type="COPY_CODE", example="F" * 16)])


# ── Component wiring ──────────────────────────────────────────────────────────


def test_buttons_component_normalizes_to_type_and_buttons_only():
    component = TemplateComponent(
        type="buttons",
        text="",
        buttons=[_quick("Book a table")],
    )
    assert _normalize_component_for_meta(component) == {
        "type": "BUTTONS",
        "buttons": [{"type": "QUICK_REPLY", "text": "Book a table"}],
    }


def test_components_are_ordered_the_way_meta_requires():
    ordered = _order_components(
        [
            {"type": "BUTTONS"},
            {"type": "FOOTER"},
            {"type": "BODY"},
            {"type": "HEADER"},
        ]
    )
    assert [c["type"] for c in ordered] == ["HEADER", "BODY", "FOOTER", "BUTTONS"]


def test_unknown_components_keep_their_relative_order_at_the_end():
    ordered = _order_components(
        [{"type": "CAROUSEL"}, {"type": "BUTTONS"}, {"type": "LIMITED_TIME_OFFER"}]
    )
    assert [c["type"] for c in ordered] == [
        "BUTTONS",
        "CAROUSEL",
        "LIMITED_TIME_OFFER",
    ]


# ── Raw row retention, found in review of #47 ─────────────────────────────────


async def test_a_numeric_zero_cell_survives_into_the_mappable_row():
    """`str(value or "")` turned a legitimate 0 into a blank, so a variable
    mapped to that column resolved empty and used its fallback instead."""
    from app.models.contact import ColumnMapping
    from app.services.contact_parser import parse_contacts

    csv = b"Name,Phone,Points,Notes\nRahul,9876543210,0,\n"
    result = await parse_contacts(csv, "guests.csv", ColumnMapping(), set())

    assert result.valid_count == 1
    row = result.valid_rows[0].row
    assert row["Points"] == "0"
    # Blank cells are still dropped — only the falsy-zero case was wrong.
    assert "Notes" not in row


async def test_headers_are_returned_for_the_mapping_step():
    from app.models.contact import ColumnMapping
    from app.services.contact_parser import parse_contacts

    csv = b"Name,Phone,Slot\nRahul,9876543210,8:30 PM\n"
    result = await parse_contacts(csv, "guests.csv", ColumnMapping(), set())
    assert result.headers == ["Name", "Phone", "Slot"]


async def test_an_over_long_cell_is_truncated_rather_than_stored_whole():
    """A sheet's free-text column is personal data the campaign cannot use —
    a template parameter is a short string."""
    from app.models.contact import ColumnMapping
    from app.services.contact_parser import MAX_CELL_CHARS, parse_contacts

    essay = "x" * (MAX_CELL_CHARS + 500)
    csv = f"Name,Phone,Notes\nRahul,9876543210,{essay}\n".encode()
    result = await parse_contacts(csv, "guests.csv", ColumnMapping(), set())
    assert len(result.valid_rows[0].row["Notes"]) == MAX_CELL_CHARS
