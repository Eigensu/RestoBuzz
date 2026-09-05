"""Single source of truth for member categories vs. segments.

A member is described by two *independent* axes, and conflating them is what
made the members page unfilterable:

  * **category** — the restaurant-configurable card type ("nfc", "ecard", or
    anything an admin adds). Stored on the member document as `type`. The set
    of valid values is per-restaurant (`restaurants.member_categories`), so
    nothing here may hardcode it.
  * **segment** — a system-defined behavioural view ("inactive", "interested",
    …). Derived from `dormancy_tier` / `tags`. A segment is NEVER stored as a
    member's `type`.

The two compose: `?category=vip&segment=inactive` is "VIP members we are
losing". Both are optional; omitting either means "no constraint on that axis".

`?type=` remains accepted as a legacy alias — `split_legacy_type` routes an old
value onto whichever axis it actually belongs to.
"""

import re
from typing import Any

# Ordered for display. `id` is the wire value; `label`/`description` are what
# the members page tabs and the campaign audience picker render, so both UIs
# stay in sync without redeclaring this list.
SEGMENT_DEFS: list[dict[str, str]] = [
    {
        "id": "interested",
        "label": "Interested",
        "description": "Replied positively to a campaign",
    },
    {
        "id": "active",
        "label": "Active",
        "description": "Visited in the last 30 days",
    },
    {
        "id": "at_risk",
        "label": "At-Risk",
        "description": "Last visit 30-60 days ago",
    },
    {
        "id": "dormant",
        "label": "Dormant",
        "description": "Last visit 60-90 days ago",
    },
    {
        "id": "lost",
        "label": "Lost",
        "description": "No visit in over 90 days",
    },
    {
        "id": "inactive",
        "label": "Inactive",
        "description": "At-Risk, Dormant, and Lost combined",
    },
]

SEGMENT_IDS: frozenset[str] = frozenset(s["id"] for s in SEGMENT_DEFS)

# Dormancy tiers that together mean "not coming back on their own".
INACTIVE_TIERS: list[str] = ["AT_RISK", "DORMANT", "LOST"]

# segment id -> stored dormancy_tier value.
_TIER_BY_SEGMENT: dict[str, str] = {
    "active": "ACTIVE",
    "at_risk": "AT_RISK",
    "dormant": "DORMANT",
    "lost": "LOST",
}

# Names an admin may not use for a category, because the filter layer would
# have to guess which axis was meant. "all" and "reservego" are sentinels the
# members page and the campaign audience picker send on the wire.
RESERVED_CATEGORY_NAMES: frozenset[str] = SEGMENT_IDS | {"all", "reservego"}


def is_segment(value: str | None) -> bool:
    """True when `value` names a behavioural segment rather than a category."""
    return bool(value) and value.strip().lower() in SEGMENT_IDS


def split_legacy_type(value: str | None) -> tuple[str | None, str | None]:
    """Route a legacy `?type=` value onto the (category, segment) axes.

    "all" (and None) constrains neither axis. A segment name lands on the
    segment axis; anything else is treated as a category, which is what makes
    admin-defined categories work without an allowlist.
    """
    if not value:
        return None, None
    normalised = value.strip().lower()
    if normalised in ("", "all"):
        return None, None
    if normalised in SEGMENT_IDS:
        return None, normalised
    return normalised, None


def resolve_axes(
    category: str | None, segment: str | None, legacy_type: str | None
) -> tuple[str | None, str | None]:
    """Normalise the three query params callers may send into two axes.

    Explicit `category`/`segment` win; `type` fills in whichever axis they left
    empty, so old links keep working while new ones can express both at once.
    """
    legacy_category, legacy_segment = split_legacy_type(legacy_type)

    resolved_category = (category or "").strip().lower() or legacy_category
    resolved_segment = (segment or "").strip().lower() or legacy_segment

    if resolved_category in ("", "all"):
        resolved_category = None
    if resolved_segment in ("", "all"):
        resolved_segment = None
    # A category that is really a segment name (an old client, or a stale
    # bookmark) belongs on the segment axis.
    if resolved_category and resolved_category in SEGMENT_IDS:
        resolved_segment = resolved_segment or resolved_category
        resolved_category = None

    return resolved_category, resolved_segment


def category_clause(category: str | None) -> dict[str, Any]:
    """Mongo clause matching one category, case-insensitively.

    Deliberately allowlist-free: any value a restaurant has configured — or
    any legacy value already sitting in the data — filters correctly.
    """
    if not category:
        return {}
    return {"type": {"$regex": f"^{re.escape(category)}$", "$options": "i"}}


def segment_clause(segment: str | None) -> dict[str, Any]:
    """Mongo clause for a behavioural segment.

    Returns {} for None or an unrecognised segment, so an unknown value shows
    everything rather than silently filtering to an arbitrary subset.
    """
    if not segment:
        return {}
    if segment == "interested":
        return {"tags": "interested"}
    if segment == "inactive":
        return {"dormancy_tier": {"$in": INACTIVE_TIERS}}
    tier = _TIER_BY_SEGMENT.get(segment)
    return {"dormancy_tier": tier} if tier else {}


def build_member_query(
    base: dict[str, Any], category: str | None, segment: str | None
) -> dict[str, Any]:
    """Compose a member query from a base filter plus both axes."""
    return {**base, **category_clause(category), **segment_clause(segment)}


def matches_segment(item: Any, segment: str | None) -> bool:
    """Segment predicate for an already-serialized member.

    The r2 path merges two sources in memory and cannot re-query, so it filters
    with this instead — same definitions as `segment_clause`, so both paths
    agree on what "dormant" means.
    """
    if not segment:
        return True
    if segment == "interested":
        return "interested" in (getattr(item, "tags", None) or [])
    tier = getattr(item, "dormancy_tier", None)
    if segment == "inactive":
        return tier in INACTIVE_TIERS
    expected = _TIER_BY_SEGMENT.get(segment)
    return tier == expected if expected else True


def matches_category(item: Any, category: str | None) -> bool:
    """Category predicate for an already-serialized member (see above)."""
    if not category:
        return True
    return (getattr(item, "type", None) or "").lower() == category.lower()


def fielia_supplies(category: str | None) -> bool:
    """Whether the external Fielia dataset can contribute to this category.

    Every Fielia card maps to type "nfc" (fielia_members_service._map_doc), so
    an unconstrained listing or an explicit "nfc" request includes them, and
    any other category cannot match a Fielia row.
    """
    return category is None or category.lower() == "nfc"
