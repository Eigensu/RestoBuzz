"""BSUID / username support.

Meta omits `wa_id` from webhooks for a user who has adopted a username and whom
the business has not interacted with in 30 days, so phone number can no longer
be assumed present on inbound traffic.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.services.meta_api import _addressing_fields, _build_payload
from app.services.wa_identity import (
    build_contact_index,
    is_bsuid,
    message_identifiers,
    resolve_contact_key,
)
from app.workers.webhook_task import _find_and_mark_replied, _handle_user_id_update


# ── identifier discrimination ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("IN.13491208655302741918", True),
        ("US.13491208655302741918", True),
        ("919876543210", False),
        ("+919876543210", False),
        ("", False),
        (None, False),
    ],
)
def test_is_bsuid_discriminates_from_phone_numbers(value, expected):
    assert is_bsuid(value) is expected


# ── the regression: a contact with no wa_id ──────────────────────────────────


def test_contact_index_survives_missing_wa_id():
    # Subscripting c["wa_id"] raised KeyError here, which propagated out of the
    # webhook task and made Celery retry the whole payload deterministically —
    # dropping every message in the batch, including ones from phone users.
    index = build_contact_index(
        [{"profile": {"name": "Ada", "username": "ada"}, "user_id": "IN.123"}]
    )
    assert index["IN.123"]["phone"] is None
    assert index["IN.123"]["username"] == "ada"
    assert index["IN.123"]["name"] == "Ada"


def test_contact_index_keys_one_entry_under_both_identifiers():
    index = build_contact_index(
        [{"profile": {"name": "Ada"}, "wa_id": "919876543210", "user_id": "IN.123"}]
    )
    assert index["919876543210"] is index["IN.123"]


def test_contact_index_tolerates_empty_and_missing_profile():
    assert build_contact_index([]) == {}
    assert build_contact_index(None) == {}
    index = build_contact_index([{"wa_id": "919876543210"}])
    assert index["919876543210"]["name"] is None


def test_message_identifiers_reads_either_field():
    assert message_identifiers({"from": "919876543210"}) == ("919876543210", None)
    assert message_identifiers({"from_user_id": "IN.123"}) == (None, "IN.123")
    assert message_identifiers({}) == (None, None)


# ── canonical key resolution ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_phone_is_preferred_over_bsuid():
    db = AsyncMock()
    assert await resolve_contact_key(db, "919876543210", "IN.123") == "919876543210"
    # No lookup needed when the phone is already in hand.
    db.wa_identities.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_bsuid_resolves_to_a_previously_linked_phone():
    # Keeps one person in one thread once their phone becomes known, instead of
    # splitting them the moment Meta stops sending it.
    db = AsyncMock()
    db.wa_identities.find_one = AsyncMock(return_value={"phone": "919876543210"})
    assert await resolve_contact_key(db, None, "IN.123") == "919876543210"


@pytest.mark.asyncio
async def test_unlinked_bsuid_falls_back_to_itself():
    db = AsyncMock()
    db.wa_identities.find_one = AsyncMock(return_value=None)
    assert await resolve_contact_key(db, None, "IN.123") == "IN.123"


@pytest.mark.asyncio
async def test_no_identifiers_resolves_to_none():
    db = AsyncMock()
    assert await resolve_contact_key(db, None, None) is None


# ── send addressing ──────────────────────────────────────────────────────────


def test_bsuid_is_addressed_via_recipient_not_to():
    # Meta rejects a BSUID sent as `to`, and `to` wins if both are present, so
    # the two fields must be mutually exclusive.
    assert _addressing_fields("IN.123") == {"recipient": "IN.123"}
    assert _addressing_fields("919876543210") == {
        "recipient_type": "individual",
        "to": "919876543210",
    }


def test_template_payload_addresses_bsuid_recipients():
    payload = _build_payload("IN.123", "tpl", {}, None, "en", None)
    assert payload["recipient"] == "IN.123"
    assert "to" not in payload

    payload = _build_payload("919876543210", "tpl", {}, None, "en", None)
    assert payload["to"] == "919876543210"
    assert "recipient" not in payload


# ── reply matching ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bsuid_key_skips_the_phone_window_fallback():
    # message_logs are keyed on recipient_phone, so there is nothing for a
    # BSUID-only sender to match against — querying anyway would scan and could
    # mark an unrelated message replied.
    db = AsyncMock()
    result = await _find_and_mark_replied(
        db, None, "IN.123", datetime.now(timezone.utc)
    )
    assert result is None
    db.message_logs.find_one_and_update.assert_not_called()


@pytest.mark.asyncio
async def test_bsuid_key_still_matches_an_explicit_context_id():
    db = AsyncMock()
    db.message_logs.find_one_and_update = AsyncMock(return_value={"job_id": "j"})
    result = await _find_and_mark_replied(
        db, "wamid.ABC", "IN.123", datetime.now(timezone.utc)
    )
    assert result == {"job_id": "j"}


# ── BSUID rotation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_id_update_carries_the_known_phone_to_the_new_bsuid():
    db = AsyncMock()
    db.wa_identities.find_one = AsyncMock(return_value={"phone": "919876543210"})

    await _handle_user_id_update(
        db, {"previous_user_id": "IN.old", "user_id": "IN.new"}
    )

    db.wa_identities.delete_one.assert_awaited_once_with({"bsuid": "IN.old"})
    update = db.wa_identities.update_one.await_args
    assert update[0][0] == {"bsuid": "IN.new"}
    assert update[0][1]["$set"]["phone"] == "919876543210"


@pytest.mark.asyncio
async def test_user_id_update_without_a_new_bsuid_is_a_noop():
    db = AsyncMock()
    await _handle_user_id_update(db, {"previous_user_id": "IN.old"})
    db.wa_identities.delete_one.assert_not_called()
    db.wa_identities.update_one.assert_not_called()
