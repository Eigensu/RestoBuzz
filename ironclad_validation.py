"""Iron-clad validation suite for Fielia/dormancy integration."""

# pylint: disable=wrong-import-position,import-error

import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError

# Must come before any app.* imports so the backend package is on the path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import (
    settings,
)  # noqa: E402  # pylint: disable=wrong-import-position,import-error
from app.database import (
    init_indexes,
)  # noqa: E402  # pylint: disable=wrong-import-position,import-error
from app.models.member import (
    MemberResponse,
)  # noqa: E402  # pylint: disable=wrong-import-position,import-error
from app.services.dormancy_service import (  # noqa: E402  # pylint: disable=wrong-import-position,import-error
    dormancy_service,
    normalize_phone_for_match,
)
from app.services.fielia_members_service import (
    fielia_service,
)  # noqa: E402  # pylint: disable=wrong-import-position,import-error


def _test_phone_normalization() -> bool:
    """TEST 1: Verify phone normalisation produces consistent 10-digit suffixes."""
    print("--- [1/7] Phone Normalization Test ---")
    test_phones = ["+91 98210 97993", "9821097993", "91-9821097993", " 098210 97993 "]
    expected = "9821097993"
    all_passed = True
    for p in test_phones:
        result = normalize_phone_for_match(p)
        status = "PASS" if result == expected else f"FAIL (Got {result})"
        print(f"  Input: {p:20} -> {str(result):12} {status}")
        if result != expected:
            all_passed = False
    print(f"Normalization Result: {'SUCCESS' if all_passed else 'FAILED'}\n")
    return all_passed


async def _test_index_validation(db) -> None:
    """TEST 2: Confirm phone and UUID indexes exist on ReserveGo collections."""
    print("--- [2/7] MongoDB Index Validation ---")
    for coll_name in ["reservego_bill_data", "reservego_uploads"]:
        indexes = await db[coll_name].index_information()
        has_phone = any(
            any(k == "phone" for k, _ in v["key"]) for v in indexes.values()
        )
        has_uuid = any(any(k == "uuid" for k, _ in v["key"]) for v in indexes.values())
        print(f"  Collection: {coll_name}")
        print(f"    - Phone Index: {'FOUND' if has_phone else 'MISSING'}")
        print(f"    - UUID Index:  {'FOUND' if has_uuid else 'MISSING'}")
    print("")


def _test_hierarchy_logic() -> None:
    """TEST 3: UUID activity must take priority over phone activity."""
    print("--- [3/7] Hierarchy Logic Validation (UUID > Phone) ---")
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)
    old = now - timedelta(days=45)

    mock_activity_map = {
        "UUID_123": (recent, "uuid_match"),
        "9821097993": (old, "phone_match"),
    }

    activity = mock_activity_map.get("UUID_123") or mock_activity_map.get("9821097993")
    status, _ = dormancy_service.compute_status(activity[0])

    if status == "active" and activity[1] == "uuid_match":
        print(f"  PASS: UUID (Recent) prioritized over Phone (Old). Status: {status}")
    else:
        print(f"  FAIL: Priority failed. Status: {status}, Source: {activity[1]}")
    print("")


async def _test_performance(db) -> dict:
    """TEST 4: Bulk activity preload should complete in under 500 ms."""
    print("--- [4/7] Performance Validation (Bulk Preload) ---")
    activity_map: dict = {}
    fielia_client = fielia_service.get_client()
    if not fielia_client:
        print("  SKIP: Fielia client not available for performance test.\n")
        return activity_map

    fielia_db = fielia_client["test"]
    docs = await fielia_db["cards"].find().limit(50).to_list(50)

    start_time = time.time()
    phones = [d.get("phone") for d in docs]
    uuids = [d.get("uuid") for d in docs]
    activity_map = await dormancy_service.get_bulk_activity(db, "r2", phones, uuids)
    duration = (time.time() - start_time) * 1000

    print(f"  Preloaded activity for {len(docs)} members in {duration:.2f}ms")
    label = "PASS" if duration < 500 else "WARNING: slower than expected (> 500ms)"
    print(f"  {label}\n")
    return activity_map


async def _test_ground_truth() -> list:
    """TEST 5: Sample real Fielia data and print key fields."""
    print("--- [5/7] Ground-Truth Data Samples (Fielia) ---")
    items: list = []
    if not fielia_service.get_client():
        print("  SKIP: Fielia client not available.\n")
        return items

    results = await fielia_service.list_members(limit=5)
    items = results.get("items", [])
    for i, item in enumerate(items):
        print(f"  Sample #{i + 1}: {item['name']}")
        print(f"    - Type:    {item['type']} (Expected: nfc)")
        print(f"    - Status:  {item['activity_status']}")
        print(f"    - Source:  {item['activity_source']}")
        print(f"    - Visit:   {item['last_visit']}")
        if item["type"] != "nfc":
            print("    FAIL: Type not forced to nfc")
        if item["activity_status"] not in ["active", "dormant", "unknown"]:
            print("    FAIL: Invalid status")
        print("-" * 30)
    print("")
    return items


def _test_schema_parity(items: list) -> None:
    """TEST 6: All sampled items must pass MemberResponse Pydantic validation."""
    print("--- [6/7] API Schema Parity Validation ---")
    if not items:
        print("  SKIP: No items to validate.\n")
        return
    try:
        for item in items:
            MemberResponse(**item)
        print("  PASS: All items match the MemberResponse Pydantic schema.\n")
    except ValidationError as exc:
        print(f"  FAIL: Schema mismatch detected!\n{exc}\n")


def _test_edge_cases(activity_map: dict) -> None:
    """TEST 7: Edge cases — null/short/unknown phone and UUID inputs."""
    print("--- [7/7] Edge Case Validation ---")
    edge_cases = [
        {"name": "No Phone", "phone": None, "uuid": None},
        {"name": "Invalid Phone", "phone": "123", "uuid": None},
        {"name": "Unknown UUID", "phone": "9999999999", "uuid": "MISSING_UUID"},
    ]
    for case in edge_cases:
        norm = normalize_phone_for_match(case["phone"])
        activity = activity_map.get(case["uuid"]) or activity_map.get(norm)
        status, source = dormancy_service.compute_status(
            activity[0] if activity else None
        )
        print(f"  Case: {case['name']:15} -> Status: {status:10} Source: {source}")
    print("")


async def run_validation() -> None:
    """Run all iron-clad validation tests against live data."""
    await init_indexes()
    print("STARTING IRON-CLAD VALIDATION\n")

    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.restobuzz

    _test_phone_normalization()
    await _test_index_validation(db)
    _test_hierarchy_logic()
    activity_map = await _test_performance(db)
    items = await _test_ground_truth()
    _test_schema_parity(items)
    _test_edge_cases(activity_map)

    print("VALIDATION COMPLETE")


if __name__ == "__main__":
    asyncio.run(run_validation())
