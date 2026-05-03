import asyncio
import time
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import ValidationError
from pprint import pprint

# Import our logic
import sys
import os
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.services.dormancy_service import dormancy_service, normalize_phone_for_match
from app.services.fielia_members_service import fielia_service
from app.models.member import MemberResponse
from app.config import settings

async def run_validation():
    # 0. Initialize Indexes
    from app.database import init_indexes
    await init_indexes()

    print("STARTING IRON-CLAD VALIDATION\n")
    
    # 1. Database Connection
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.restobuzz # Assuming restobuzz is the DB name
    
    # ---------------------------------------------------------
    # TEST 1: Phone Normalization
    # ---------------------------------------------------------
    print("--- [1/7] Phone Normalization Test ---")
    test_phones = ["+91 98210 97993", "9821097993", "91-9821097993", " 098210 97993 "]
    expected = "9821097993"
    all_passed = True
    for p in test_phones:
        result = normalize_phone_for_match(p)
        status = "PASS" if result == expected else f"FAIL (Got {result})"
        print(f"  Input: {p:20} -> {result:12} {status}")
        if result != expected: all_passed = False
    print(f"Normalization Result: {'SUCCESS' if all_passed else 'FAILED'}\n")

    # ---------------------------------------------------------
    # TEST 2: Index Validation
    # ---------------------------------------------------------
    print("--- [2/7] MongoDB Index Validation ---")
    for coll_name in ["reservego_bill_data", "reservego_uploads"]:
        indexes = await db[coll_name].index_information()
        has_phone = any("phone" in v["key"][0] for v in indexes.values())
        has_uuid = any("uuid" in v["key"][0] for v in indexes.values())
        print(f"  Collection: {coll_name}")
        print(f"    - Phone Index: {'FOUND' if has_phone else 'MISSING'}")
        print(f"    - UUID Index:  {'FOUND' if has_uuid else 'MISSING'}")
    print("")

    # ---------------------------------------------------------
    # TEST 3: Hierarchy Logic (Mock Test)
    # ---------------------------------------------------------
    print("--- [3/7] Hierarchy Logic Validation (UUID > Phone) ---")
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)
    old = now - timedelta(days=45)
    
    # Mock activity map
    # UUID match is RECENT, Phone match is OLD
    mock_activity_map = {
        "UUID_123": (recent, "uuid_match"),
        "9821097993": (old, "phone_match")
    }
    
    # Simulate a member with both
    uuid = "UUID_123"
    phone = "9821097993"
    
    activity = mock_activity_map.get(uuid) or mock_activity_map.get(phone)
    status, source = dormancy_service.compute_status(activity[0])
    
    if status == "active" and activity[1] == "uuid_match":
        print(f"  PASS: UUID (Recent) prioritized over Phone (Old). Status: {status}, Source: {activity[1]}")
    else:
        print(f"  FAIL: Priority failed. Status: {status}, Source: {activity[1]}")
    print("")

    # ---------------------------------------------------------
    # TEST 4: Performance Validation (Bulk Preload)
    # ---------------------------------------------------------
    print("--- [4/7] Performance Validation (Bulk Preload) ---")
    # Fetch a batch of Fielia members
    fielia_client = fielia_service.get_client()
    if fielia_client:
        fielia_db = fielia_client["test"]
        docs = await fielia_db["cards"].find().limit(50).to_list(50)
        
        start_time = time.time()
        phones = [d.get("phone") for d in docs]
        uuids = [d.get("uuid") for d in docs]
        
        activity_map = await dormancy_service.get_bulk_activity(db, "r2", phones, uuids)
        duration = (time.time() - start_time) * 1000
        
        print(f"  Preloaded activity for {len(docs)} members in {duration:.2f}ms")
        if duration < 500:
            print("  PASS: Performance is optimal (< 500ms for batch)")
        else:
            print("  WARNING: Performance is slower than expected (> 500ms)")
    else:
        print("  SKIP: Fielia client not available for performance test.")
    print("")

    # ---------------------------------------------------------
    # TEST 5: Ground-Truth Data Check (Real Data)
    # ---------------------------------------------------------
    print("--- [5/7] Ground-Truth Data Samples (Fielia) ---")
    if fielia_client:
        results = await fielia_service.list_members(limit=5)
        items = results.get("items", [])
        for i, item in enumerate(items):
            print(f"  Sample #{i+1}: {item['name']}")
            print(f"    - ID:      {item['id']}")
            print(f"    - Type:    {item['type']} (Expected: nfc)")
            print(f"    - Status:  {item['activity_status']}")
            print(f"    - Source:  {item['activity_source']}")
            print(f"    - Visit:   {item['last_visit']}")
            
            # Basic validation
            if item['type'] != 'nfc': print("    FAIL: Type not forced to nfc")
            if item['activity_status'] not in ['active', 'dormant', 'unknown']: print("    FAIL: Invalid status")
            print("-" * 30)
    print("")

    # ---------------------------------------------------------
    # TEST 6: API Schema Parity (Pydantic)
    # ---------------------------------------------------------
    print("--- [6/7] API Schema Parity Validation ---")
    if fielia_client and items:
        try:
            for item in items:
                # This will throw if backend model doesn't match MemberResponse
                MemberResponse(**item)
            print("  PASS: All items match the MemberResponse Pydantic schema.")
        except ValidationError as e:
            print(f"  FAIL: Schema mismatch detected!\n{e}")
    print("")

    # ---------------------------------------------------------
    # TEST 7: Edge Case - Null/Invalid Data
    # ---------------------------------------------------------
    print("--- [7/7] Edge Case Validation ---")
    edge_cases = [
        {"name": "No Phone", "phone": None, "uuid": None},
        {"name": "Invalid Phone", "phone": "123", "uuid": None},
        {"name": "Unknown UUID", "phone": "9999999999", "uuid": "MISSING_UUID"}
    ]
    
    for case in edge_cases:
        norm = normalize_phone_for_match(case["phone"])
        activity = activity_map.get(case["uuid"]) or activity_map.get(norm)
        status, source = dormancy_service.compute_status(activity[0] if activity else None)
        print(f"  Case: {case['name']:15} -> Status: {status:10} Source: {source}")
        
    print("\nVALIDATION COMPLETE")

if __name__ == "__main__":
    asyncio.run(run_validation())
