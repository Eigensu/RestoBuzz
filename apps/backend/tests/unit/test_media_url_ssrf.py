"""Destination checks on the operator-supplied media URL.

Both template editors and the campaign wizard offer a "paste a URL" box beside
the uploader, and the backend fetches whatever is typed there server-side
before handing the bytes to Meta. Unchecked, that is an SSRF primitive: an
admin can aim it at loopback, a private range or a cloud metadata address and
have the response uploaded to Meta. Redirects were followed automatically, so a
public URL could bounce the fetch onto a private one after the fact.

Also pins that a malformed URL comes back as a MetaAPIError. httpx.InvalidURL
does not derive from httpx.RequestError, so uncaught it escapes both callers'
handlers — create_campaign's `except MetaAPIError` misses it, the request 500s,
and the draft campaign_job inserted moments earlier is never rolled back.
"""

import httpx
import pytest

from app.services import meta_api
from app.services.meta_api import MetaAPIError, _fetch_media_bytes

PUBLIC_IP = "93.184.216.34"

# Every range an operator could aim the fetch at from inside the platform.
BLOCKED_ADDRESSES = [
    ("127.0.0.1", "loopback"),
    ("::1", "ipv6-loopback"),
    ("10.0.0.5", "private-10"),
    ("172.16.4.2", "private-172"),
    ("192.168.1.10", "private-192"),
    ("169.254.169.254", "cloud-metadata"),
    ("100.64.0.1", "carrier-nat"),
    ("0.0.0.0", "unspecified"),
    ("fd00::1", "ipv6-unique-local"),
]


@pytest.fixture
def resolves_to(monkeypatch):
    """Point every hostname at a chosen address, without touching real DNS."""

    def install(*addresses):
        async def fake(host):
            return list(addresses)

        monkeypatch.setattr(meta_api, "_resolve_host", fake)

    return install


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )


def _ok(request):
    return httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"movie")


# ── Non-public destinations are refused before the request is made ────────────


@pytest.mark.parametrize(
    "address", [a for a, _ in BLOCKED_ADDRESSES], ids=[i for _, i in BLOCKED_ADDRESSES]
)
async def test_non_public_address_is_rejected(resolves_to, address):
    resolves_to(address)
    requested = []

    def handler(request):
        requested.append(request.url)
        return _ok(request)

    async with _client(handler) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://internal.example/clip.mp4")

    assert excinfo.value.code == "media_url_rejected"
    # Refused outright — the fetch never left the process.
    assert requested == []


async def test_a_single_private_answer_rejects_a_multi_homed_host(resolves_to):
    """One public A record must not launder a private one on the same name."""
    resolves_to(PUBLIC_IP, "127.0.0.1")

    async with _client(_ok) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://mixed.example/clip.mp4")

    assert excinfo.value.code == "media_url_rejected"


async def test_public_address_is_fetched(resolves_to):
    resolves_to(PUBLIC_IP)

    async with _client(_ok) as client:
        content, content_type = await _fetch_media_bytes(
            client, "https://cdn.example/clip.mp4"
        )

    assert content == b"movie"
    assert content_type == "video/mp4"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://cdn.example/clip.mp4",
        "gopher://cdn.example/clip.mp4",
        "data:video/mp4;base64,AAAA",
    ],
)
async def test_non_http_schemes_are_rejected(resolves_to, url):
    resolves_to(PUBLIC_IP)

    async with _client(_ok) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, url)

    assert excinfo.value.code == "media_url_rejected"


async def test_unresolvable_host_is_rejected():
    """A name that resolves to nothing is a rejection, not a stray gaierror."""

    async with _client(_ok) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(
                client, "https://no-such-host.invalid/clip.mp4"
            )

    assert excinfo.value.code == "media_url_rejected"


# ── Redirects are followed by hand, and re-checked at every hop ───────────────


async def test_redirect_onto_a_private_address_is_rejected(monkeypatch):
    """The whole point of turning follow_redirects off: hop 2 gets checked too."""

    async def fake_resolve(host):
        return [PUBLIC_IP] if host == "cdn.example" else ["169.254.169.254"]

    monkeypatch.setattr(meta_api, "_resolve_host", fake_resolve)
    reached = []

    def handler(request):
        reached.append(request.url.host)
        if request.url.host == "cdn.example":
            return httpx.Response(302, headers={"location": "http://metadata.internal/"})
        return _ok(request)

    async with _client(handler) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://cdn.example/clip.mp4")

    assert excinfo.value.code == "media_url_rejected"
    assert reached == ["cdn.example"]


async def test_redirect_to_a_public_address_is_followed(resolves_to):
    resolves_to(PUBLIC_IP)

    def handler(request):
        if request.url.path == "/clip.mp4":
            return httpx.Response(302, headers={"location": "/real/clip.mp4"})
        return _ok(request)

    async with _client(handler) as client:
        content, _ = await _fetch_media_bytes(client, "https://cdn.example/clip.mp4")

    assert content == b"movie"


async def test_redirect_loop_is_capped(resolves_to):
    resolves_to(PUBLIC_IP)

    def handler(request):
        return httpx.Response(302, headers={"location": "https://cdn.example/again"})

    async with _client(handler) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://cdn.example/clip.mp4")

    assert excinfo.value.code == "media_fetch_failed"
    assert "redirected" in excinfo.value.message


async def test_redirect_without_a_location_is_an_error(resolves_to):
    resolves_to(PUBLIC_IP)

    def handler(request):
        return httpx.Response(302)

    async with _client(handler) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://cdn.example/clip.mp4")

    assert excinfo.value.code == "media_fetch_failed"


# ── A malformed URL is a MetaAPIError, not an escaping httpx.InvalidURL ───────


def test_invalid_url_does_not_derive_from_request_error():
    """The reason the conversion below is needed at all."""
    assert not issubclass(httpx.InvalidURL, httpx.RequestError)


async def test_malformed_url_becomes_a_meta_api_error(resolves_to):
    """Passes the destination check, then httpx rejects it building the request."""
    resolves_to(PUBLIC_IP)

    async with _client(_ok) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://cdn.example:abc/clip.mp4")

    assert excinfo.value.code == "media_url_rejected"


async def test_malformed_ipv6_literal_is_rejected(resolves_to):
    """urlsplit itself raises on this one, before any resolution happens."""
    resolves_to(PUBLIC_IP)

    async with _client(_ok) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https://[not-ipv6/clip.mp4")

    assert excinfo.value.code == "media_url_rejected"


async def test_url_with_no_host_is_rejected(resolves_to):
    resolves_to(PUBLIC_IP)

    async with _client(_ok) as client:
        with pytest.raises(MetaAPIError) as excinfo:
            await _fetch_media_bytes(client, "https:///clip.mp4")

    assert excinfo.value.code == "media_url_rejected"
