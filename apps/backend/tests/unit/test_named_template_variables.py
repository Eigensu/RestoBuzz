"""Named template variables, and mapping them to per-recipient data.

Two formats now coexist: templates created before named support carry {{1}},
{{2}} and are matched by position, while new ones carry {{customer_name}} and
are matched by name. Meta fixes the format when the template is created and it
can never be changed, so both paths stay alive indefinitely.
"""

import pytest

from app.core.errors import ValidationError
from app.models.campaign import VariableSource
from app.routers.campaigns import (
    _campaign_wide_variables,
    _require_variable_coverage,
    _resolve_recipient_variables,
    _template_body_var_keys,
)
from app.routers.templates import (
    TemplateComponent,
    _extract_variables,
    _normalize_component_for_meta,
    _resolve_parameter_format,
)
from app.services.meta_api import _build_payload


def _body(text: str) -> TemplateComponent:
    return TemplateComponent(type="BODY", text=text)


# ── Format detection ──────────────────────────────────────────────────────────


def test_numbered_placeholders_stay_positional():
    assert _resolve_parameter_format([_body("Hi {{1}}, table at {{2}}")]) == "POSITIONAL"


def test_named_placeholders_select_the_named_format():
    assert (
        _resolve_parameter_format([_body("Hi {{customer_name}} at {{venue}}")])
        == "NAMED"
    )


def test_a_template_with_no_variables_is_positional():
    assert _resolve_parameter_format([_body("Our kitchen is open again.")]) == "POSITIONAL"


def test_mixing_the_two_formats_is_rejected_with_both_offenders():
    with pytest.raises(ValidationError, match=r"\{\{1\}\} and \{\{customer_name\}\}"):
        _resolve_parameter_format([_body("Hi {{1}}, welcome to {{customer_name}}")])


def test_variable_names_are_deduplicated_in_appearance_order():
    assert _extract_variables("{{b}} then {{a}} then {{b}} again") == ["b", "a"]


def test_header_text_counts_toward_format_detection():
    components = [
        TemplateComponent(type="HEADER", format="TEXT", text="{{offer_name}}"),
        _body("Details inside."),
    ]
    assert _resolve_parameter_format(components) == "NAMED"


# ── Examples Meta requires ────────────────────────────────────────────────────


def test_named_body_gets_named_example_params():
    data = _normalize_component_for_meta(_body("Hi {{customer_name}}"), "NAMED")
    assert data["example"] == {
        "body_text_named_params": [
            {"param_name": "customer_name", "example": "Customer Name"}
        ]
    }


def test_a_sample_typed_by_the_author_is_kept():
    component = TemplateComponent(
        type="BODY",
        text="Hi {{customer_name}}",
        example={
            "body_text_named_params": [
                {"param_name": "customer_name", "example": "Rahul"}
            ]
        },
    )
    data = _normalize_component_for_meta(component, "NAMED")
    assert data["example"]["body_text_named_params"] == [
        {"param_name": "customer_name", "example": "Rahul"}
    ]


def test_positional_examples_are_untouched_by_named_support():
    data = _normalize_component_for_meta(_body("Hi {{1}} and {{2}}"), "POSITIONAL")
    assert data["example"] == {"body_text": [["value_1", "value_2"]]}


def test_named_text_header_gets_its_own_example_block():
    component = TemplateComponent(type="HEADER", format="TEXT", text="{{offer_name}}")
    data = _normalize_component_for_meta(component, "NAMED")
    assert data["example"] == {
        "header_text_named_params": [
            {"param_name": "offer_name", "example": "Offer Name"}
        ]
    }


# ── Send payload ──────────────────────────────────────────────────────────────


def test_positional_send_orders_parameters_numerically():
    """Position is the entire contract for {{1}}/{{2}} — 10 must not sort before 2."""
    payload = _build_payload(
        "+919876543210",
        "tpl",
        {"2": "second", "10": "tenth", "1": "first"},
        None,
    )
    body = payload["template"]["components"][0]
    assert [p["text"] for p in body["parameters"]] == ["first", "second", "tenth"]
    assert "parameter_name" not in body["parameters"][0]


def test_named_send_labels_each_parameter():
    payload = _build_payload(
        "+919876543210",
        "tpl",
        {"customer_name": "Rahul", "venue": "Fielia Soraia"},
        None,
    )
    body = payload["template"]["components"][0]
    assert body["parameters"] == [
        {"type": "text", "parameter_name": "customer_name", "text": "Rahul"},
        {"type": "text", "parameter_name": "venue", "text": "Fielia Soraia"},
    ]


# ── Mapping variables to recipients ───────────────────────────────────────────


def test_named_variables_are_discovered_on_the_template():
    doc = {"components": [{"type": "BODY", "text": "Hi {{customer_name}} at {{venue}}"}]}
    assert _template_body_var_keys(doc) == {"customer_name", "venue"}


def test_a_column_source_reads_that_recipients_own_cell():
    resolved = _resolve_recipient_variables(
        {"name": "Rahul", "row": {"Guest Name": "Rahul", "Slot": "8:30 PM"}},
        sources={
            "customer_name": VariableSource(kind="column", column="Guest Name"),
            "booking_time": VariableSource(kind="column", column="Slot"),
        },
        campaign_variables={},
        allowed_keys={"customer_name", "booking_time"},
    )
    assert resolved == {"customer_name": "Rahul", "booking_time": "8:30 PM"}


def test_a_blank_cell_falls_back_instead_of_failing_the_send():
    resolved = _resolve_recipient_variables(
        {"name": "", "row": {"Guest Name": ""}},
        sources={
            "customer_name": VariableSource(
                kind="column", column="Guest Name", fallback="there"
            )
        },
        campaign_variables={},
        allowed_keys={"customer_name"},
    )
    assert resolved == {"customer_name": "there"}


def test_the_recipients_own_value_beats_the_campaign_wide_one():
    resolved = _resolve_recipient_variables(
        {"row": {"Guest Name": "Rahul"}},
        sources={"customer_name": VariableSource(kind="column", column="Guest Name")},
        campaign_variables={"customer_name": "Valued Guest"},
        allowed_keys={"customer_name"},
    )
    assert resolved == {"customer_name": "Rahul"}


def test_a_contact_source_uses_the_detected_name_not_a_column():
    resolved = _resolve_recipient_variables(
        {"name": "Rahul", "row": {}},
        sources={"customer_name": VariableSource(kind="contact")},
        campaign_variables={},
        allowed_keys={"customer_name"},
    )
    assert resolved == {"customer_name": "Rahul"}


def test_variables_mapped_before_variable_sources_existed_still_resolve():
    """Contact files cached by the old upload-time mapping carry `variables`."""
    resolved = _resolve_recipient_variables(
        {"variables": {"1": "Rahul"}},
        sources={},
        campaign_variables={},
        allowed_keys={"1"},
    )
    assert resolved == {"1": "Rahul"}


# ── Restaurant-sourced values ─────────────────────────────────────────────────


def test_restaurant_name_is_read_from_the_sending_restaurant():
    """Typing it by hand is how one venue's campaign goes out under another's name."""
    resolved = _campaign_wide_variables(
        {"venue": VariableSource(kind="restaurant", field="name")},
        {"name": "Fielia Soraia", "location": "Goa"},
    )
    assert resolved == {"venue": "Fielia Soraia"}


def test_an_unknown_restaurant_field_is_rejected():
    with pytest.raises(ValidationError, match="unknown restaurant field"):
        _campaign_wide_variables(
            {"venue": VariableSource(kind="restaurant", field="wa_phones")},
            {"name": "Fielia Soraia"},
        )


def test_column_sources_contribute_nothing_campaign_wide():
    assert (
        _campaign_wide_variables(
            {"customer_name": VariableSource(kind="column", column="Guest Name")},
            {"name": "Fielia Soraia"},
        )
        == {}
    )


# ── Coverage guard ────────────────────────────────────────────────────────────


def test_a_variable_with_neither_value_nor_fallback_blocks_the_campaign():
    with pytest.raises(ValidationError, match=r"\{\{customer_name\}\}"):
        _require_variable_coverage(
            {"customer_name"},
            {"customer_name": VariableSource(kind="column", column="Guest Name")},
            {},
        )


def test_a_fallback_satisfies_the_coverage_guard():
    _require_variable_coverage(
        {"customer_name"},
        {
            "customer_name": VariableSource(
                kind="column", column="Guest Name", fallback="there"
            )
        },
        {},
    )


def test_a_campaign_wide_value_satisfies_the_coverage_guard():
    _require_variable_coverage({"venue"}, {}, {"venue": "Fielia Soraia"})
