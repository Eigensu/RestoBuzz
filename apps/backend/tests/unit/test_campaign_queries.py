"""Query-shape tests for the campaign list and retry-chain filters.

These guard two bugs that made campaigns silently invisible:
  * retry children counting against the list page size, collapsing a page of N
    documents into far fewer real campaigns;
  * the retry-chain query comparing parent_campaign_id (a string) against an
    ObjectId, so it matched no children at all.
"""

from bson import ObjectId

from app.routers.campaigns import _ROOT_ONLY_FILTER, _retry_chain_filter


def _matches(flt: dict, doc: dict) -> bool:
    """Evaluate the tiny subset of Mongo query syntax these filters use."""
    for key, cond in flt.items():
        if key == "$or":
            if not any(_matches(branch, doc) for branch in cond):
                return False
        elif isinstance(cond, dict) and "$exists" in cond:
            if (key in doc) != cond["$exists"]:
                return False
        elif isinstance(cond, dict) and "$in" in cond:
            if doc.get(key) not in cond["$in"]:
                return False
        elif doc.get(key) != cond:
            return False
    return True


def test_root_filter_matches_campaigns_without_a_parent():
    # Field absent entirely (campaigns created before smart retries existed)
    assert _matches(_ROOT_ONLY_FILTER, {"name": "launch"})
    # Field present but null
    assert _matches(_ROOT_ONLY_FILTER, {"name": "launch", "parent_campaign_id": None})


def test_root_filter_excludes_retry_children():
    child = {"name": "launch (retry)", "parent_campaign_id": str(ObjectId())}
    assert not _matches(_ROOT_ONLY_FILTER, child)


def test_chain_filter_matches_root_by_object_id():
    root_oid = ObjectId()
    flt = _retry_chain_filter(root_oid)
    assert _matches(flt, {"_id": root_oid})


def test_chain_filter_matches_children_by_string_parent_id():
    # The regression: children store parent_campaign_id as a string, so the
    # filter must compare against str(root_oid), not the ObjectId itself.
    root_oid = ObjectId()
    flt = _retry_chain_filter(root_oid)
    assert _matches(flt, {"_id": ObjectId(), "parent_campaign_id": str(root_oid)})


def test_chain_filter_uses_correct_types_on_each_branch():
    root_oid = ObjectId()
    branches = _retry_chain_filter(root_oid)["$or"]
    id_branch = next(b for b in branches if "_id" in b)
    parent_branch = next(b for b in branches if "parent_campaign_id" in b)
    assert isinstance(id_branch["_id"], ObjectId)
    assert isinstance(parent_branch["parent_campaign_id"], str)


def test_chain_filter_accepts_a_string_root_id():
    # Callers resolve the root from parent_campaign_id, which is a string.
    root_oid = ObjectId()
    flt = _retry_chain_filter(str(root_oid))
    assert _matches(flt, {"_id": root_oid})
    assert _matches(flt, {"_id": ObjectId(), "parent_campaign_id": str(root_oid)})


def test_chain_filter_excludes_unrelated_campaigns():
    flt = _retry_chain_filter(ObjectId())
    other = {"_id": ObjectId(), "parent_campaign_id": str(ObjectId())}
    assert not _matches(flt, other)
