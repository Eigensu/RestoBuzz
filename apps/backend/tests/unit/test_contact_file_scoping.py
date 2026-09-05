"""A contact file reference must not be usable by anyone who holds it.

Both campaign-create endpoints took `contact_file_ref` from the request body and
looked it up by reference alone. `validate_restaurant_access` checks the caller
can reach the restaurant they named — never that the contact list is theirs. A
caller holding someone else's reference could therefore send a real campaign to
that account's guest list, then read the recipients back out of their own
message logs. The reference is a UUID4: unguessable, but it travels in API
responses, browser network logs and support threads, so it is not a permission.
"""

import json

import pytest

from app.core.errors import ContactFileExpiredError
from app.services import contact_files
from app.services.contact_files import cache_key, load_contacts

OWNER = "user_owner"
STRANGER = "user_stranger"
FILE_REF = "6f1e9c1a-0000-4000-8000-000000000001"
ROWS = [{"name": "Rahul", "phone": "+919876543210"}]


class _FakeRedis:
    """Only what load_contacts touches."""

    def __init__(self, store=None):
        self.store = store or {}

    async def get(self, key):
        return self.store.get(key)

    async def aclose(self):
        return None


class _FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query):
        return next(
            (d for d in self.docs if all(d.get(k) == v for k, v in query.items())),
            None,
        )


class _FakeDB:
    def __init__(self, docs):
        self.contact_files = _FakeCollection(docs)


@pytest.fixture
def saved_upload():
    """One upload owned by OWNER, as `contact_files` stores it."""
    return [
        {
            "result.file_ref": FILE_REF,
            "uploaded_by": OWNER,
            "result": {"file_ref": FILE_REF, "valid_rows": ROWS},
        }
    ]


@pytest.fixture
def no_cache(monkeypatch):
    """Force the Mongo path."""
    monkeypatch.setattr(contact_files, "from_url", lambda *a, **k: _FakeRedis())


# ── The cache key carries the owner ───────────────────────────────────────────


def test_the_same_reference_is_a_different_key_per_owner():
    assert cache_key(FILE_REF, OWNER) != cache_key(FILE_REF, STRANGER)


def test_the_owner_precedes_the_reference_in_the_key():
    assert cache_key(FILE_REF, OWNER) == f"file_ref:{OWNER}:{FILE_REF}"


# ── Mongo path ────────────────────────────────────────────────────────────────


async def test_the_owner_can_load_their_own_upload(saved_upload, no_cache):
    rows = await load_contacts(_FakeDB(saved_upload), FILE_REF, OWNER)
    assert rows == ROWS


async def test_a_stranger_holding_the_reference_cannot_load_it(
    saved_upload, no_cache
):
    with pytest.raises(ContactFileExpiredError):
        await load_contacts(_FakeDB(saved_upload), FILE_REF, STRANGER)


async def test_an_unknown_reference_reads_as_expired(no_cache):
    with pytest.raises(ContactFileExpiredError):
        await load_contacts(_FakeDB([]), FILE_REF, OWNER)


# ── Redis path ────────────────────────────────────────────────────────────────


async def test_a_cached_list_is_served_to_its_owner(monkeypatch):
    cached = _FakeRedis({cache_key(FILE_REF, OWNER): json.dumps(ROWS)})
    monkeypatch.setattr(contact_files, "from_url", lambda *a, **k: cached)
    rows = await load_contacts(_FakeDB([]), FILE_REF, OWNER)
    assert rows == ROWS


async def test_a_cached_list_is_not_served_to_a_stranger(monkeypatch):
    """A member list lives only in Redis, so the key scoping is the whole
    control for that source — there is no Mongo copy to fall back to."""
    cached = _FakeRedis({cache_key(FILE_REF, OWNER): json.dumps(ROWS)})
    monkeypatch.setattr(contact_files, "from_url", lambda *a, **k: cached)
    with pytest.raises(ContactFileExpiredError):
        await load_contacts(_FakeDB([]), FILE_REF, STRANGER)


async def test_a_cache_outage_still_serves_the_owner_from_mongo(
    saved_upload, monkeypatch
):
    def explode(*_a, **_k):
        raise OSError("redis down")

    monkeypatch.setattr(contact_files, "from_url", explode)
    rows = await load_contacts(_FakeDB(saved_upload), FILE_REF, OWNER)
    assert rows == ROWS


async def test_a_cache_outage_does_not_open_the_gap_for_a_stranger(
    saved_upload, monkeypatch
):
    def explode(*_a, **_k):
        raise OSError("redis down")

    monkeypatch.setattr(contact_files, "from_url", explode)
    with pytest.raises(ContactFileExpiredError):
        await load_contacts(_FakeDB(saved_upload), FILE_REF, STRANGER)


# ── Cache-write failure, found in review of #49 ───────────────────────────────


async def test_cache_contacts_reports_success(monkeypatch):
    class _Writable(_FakeRedis):
        async def ping(self):
            return True

        async def set(self, key, value, ex=None):
            self.store[key] = value

    written = _Writable()
    monkeypatch.setattr(contact_files, "from_url", lambda *a, **k: written)

    class _Row:
        @staticmethod
        def model_dump():
            return ROWS[0]

    assert await contact_files.cache_contacts(FILE_REF, [_Row()], OWNER) is True
    assert cache_key(FILE_REF, OWNER) in written.store


async def test_cache_contacts_reports_failure_instead_of_raising(monkeypatch):
    """A caller with a durable copy needs the request to survive a cache
    outage; one without a durable copy needs to know it failed."""

    def explode(*_a, **_k):
        raise OSError("redis down")

    monkeypatch.setattr(contact_files, "from_url", explode)
    assert await contact_files.cache_contacts(FILE_REF, [], OWNER) is False
