"""Regression tests for Meta template fetching.

The sync endpoint used to hang (nginx 499 after ~2min) because httpx REPLACES
a URL's query string when `params` is passed, so re-sending params while
following `paging.next` stripped the cursor and refetched page 1 forever.
"""

import httpx
import pytest

from app.services import meta_api


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture
def patched_client(monkeypatch):
    """Route every AsyncClient created inside meta_api through a mock transport."""

    def install(handler):
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = _mock_transport(handler)
            return original(*args, **kwargs)

        monkeypatch.setattr(meta_api.httpx, "AsyncClient", factory)

    return install


@pytest.mark.asyncio
async def test_fetch_templates_follows_cursor_without_stripping_it(patched_client):
    calls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        after = request.url.params.get("after")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "1", "name": "a", "language": "en_US"}],
                    "paging": {
                        "next": "https://graph.facebook.com/v20.0/W/message_templates"
                        "?access_token=tok&after=CURSOR&limit=100"
                    },
                },
            )
        assert after == "CURSOR", "cursor was stripped from the next-page URL"
        return httpx.Response(
            200,
            json={"data": [{"id": "2", "name": "b", "language": "en_US"}]},
        )

    patched_client(handler)

    templates = await meta_api.fetch_templates("W", "tok")

    assert [t["name"] for t in templates] == ["a", "b"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_fetch_templates_requests_id_field(patched_client):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["fields"] = request.url.params.get("fields")
        return httpx.Response(200, json={"data": []})

    patched_client(handler)
    await meta_api.fetch_templates("W", "tok")

    # meta_id is what PATCH /templates keys off — it must be requested.
    assert "id" in (seen["fields"] or "").split(",")


@pytest.mark.asyncio
async def test_fetch_templates_terminates_on_endless_next(patched_client):
    """Meta keeps returning `paging.next` past the last page — an empty data
    array is the real terminator, and the page cap is the backstop."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "data": [{"id": str(calls["n"]), "name": f"t{calls['n']}"}],
                "paging": {
                    "next": f"https://graph.facebook.com/v20.0/W/message_templates"
                    f"?access_token=tok&after=C{calls['n']}&limit=100"
                },
            },
        )

    patched_client(handler)
    templates = await meta_api.fetch_templates("W", "tok")

    assert calls["n"] == meta_api.MAX_TEMPLATE_PAGES
    assert len(templates) == meta_api.MAX_TEMPLATE_PAGES


@pytest.mark.asyncio
async def test_fetch_templates_stops_on_empty_page(patched_client):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "1", "name": "a"}],
                    "paging": {
                        "next": "https://graph.facebook.com/v20.0/W/message_templates"
                        "?access_token=tok&after=C1&limit=100"
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [],
                "paging": {
                    "next": "https://graph.facebook.com/v20.0/W/message_templates"
                    "?access_token=tok&after=C2&limit=100"
                },
            },
        )

    patched_client(handler)
    templates = await meta_api.fetch_templates("W", "tok")

    assert len(templates) == 1
    assert calls["n"] == 2


# ── Template edit: buttons added in Meta Business Manager ────────────────────


def test_edit_preserves_buttons_the_editor_drops():
    """The UI strips BUTTONS on load, and Meta's edit replaces the whole
    component set — so a body-only edit must not delete the buttons."""
    from app.routers.templates import _preserve_unmanaged_components

    stored = {
        "name": "promo",
        "restaurant_id": "r1",
        "components": [
            {"type": "BODY", "text": "old"},
            {
                "type": "BUTTONS",
                "buttons": [{"type": "QUICK_REPLY", "text": "Book now"}],
            },
        ],
    }
    incoming = [{"type": "BODY", "text": "new"}]

    result = _preserve_unmanaged_components(incoming, stored)

    assert [c["type"] for c in result] == ["BODY", "BUTTONS"]
    assert result[-1]["buttons"] == [{"type": "QUICK_REPLY", "text": "Book now"}]


def test_edit_does_not_duplicate_buttons_when_client_sends_them():
    from app.routers.templates import _preserve_unmanaged_components

    stored = {
        "components": [
            {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Old"}]}
        ]
    }
    incoming = [
        {"type": "BODY", "text": "hi"},
        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "New"}]},
    ]

    result = _preserve_unmanaged_components(incoming, stored)

    assert result == incoming


def test_edit_without_stored_buttons_is_unchanged():
    from app.routers.templates import _preserve_unmanaged_components

    incoming = [{"type": "BODY", "text": "hi"}]
    assert _preserve_unmanaged_components(incoming, {"components": []}) == incoming
    assert _preserve_unmanaged_components(incoming, {}) == incoming
