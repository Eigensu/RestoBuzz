"""
Absolute Deep Dormancy Audit.
Checks:
1. Internal members (All restaurants)
2. Fielia External members (Restaurant r2 only)
3. Historical logs (reservego_bill_data / uploads)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.config import settings
from app.services.dormancy_service import dormancy_service, normalize_phone_for_match
from app.services.fielia_members_service import fielia_service
from app.core.time import normalize_external_dt

DORMANCY_DAYS = 30


def _process_member(m, activity_map, cutoff):
    lv_candidates = []
    
    # Internal visit field
    raw_lv = m.get("last_visit")
    if raw_lv:
        if isinstance(raw_lv, str):
            raw_lv = normalize_external_dt(raw_lv)
        if raw_lv:
            lv_candidates.append(raw_lv)

    # External log match
    norm_phone = normalize_phone_for_match(m.get("phone"))
    uuid_val = m.get("card_uid")
    external_activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
    if external_activity:
        lv_candidates.append(external_activity[0])

    if not lv_candidates:
        return "unknown"
    
    final_lv = max(lv_candidates)
    
    if final_lv >= cutoff:
        return "active"
    return "dormant"

async def _process_restaurant(db, rest, cutoff):
    rid = rest.get("id") or str(rest["_id"])
    name = rest.get("name", rid)

    stats = {"active": 0, "dormant": 0, "unknown": 0, "total": 0}

    async def _handle_batch(batch):
        if not batch: return {"active": 0, "dormant": 0, "unknown": 0, "total": 0}
        
        phones = [m.get("phone") for m in batch]
        uuids = [m.get("card_uid") for m in batch]
        activity_map = await dormancy_service.get_bulk_activity(db, rid, phones, uuids)

        batch_stats = {"active": 0, "dormant": 0, "unknown": 0, "total": 0}
        for m in batch:
            batch_stats["total"] += 1
            status = _process_member(m, activity_map, cutoff)
            if status == "unknown":
                batch_stats["unknown"] += 1
            elif status == "active":
                batch_stats["active"] += 1
            else:
                batch_stats["dormant"] += 1
        return batch_stats

    def _merge_stats(target, source):
        for k in target:
            target[k] += source[k]

    # 1. Process Internal members
    internal_res = await _process_internal_members(db, rid, _handle_batch)
    _merge_stats(stats, internal_res)

    # 2. Process Fielia External members
    if rid == "r2":
        external_res = await _process_external_members(_handle_batch)
        _merge_stats(stats, external_res)

    if stats["total"] == 0:
        return

    print(f"  Restaurant : {name} ({rid})")
    print(f"  Total Pool : {stats['total']}  (Internal + External)")
    print(f"  Active     : {stats['active']}")
    print(f"  DORMANT    : {stats['dormant']}")
    print(f"  Unknown    : {stats['unknown']}")
    print("")

async def _process_internal_members(db, rid, batch_handler):
    acc = {"active": 0, "dormant": 0, "unknown": 0, "total": 0}
    batch = []
    async for m in db.members.find({"restaurant_id": rid}):
        batch.append(m)
        if len(batch) >= 100:
            res = await batch_handler(batch)
            for k in acc: acc[k] += res[k]
            batch = []
    if batch:
        res = await batch_handler(batch)
        for k in acc: acc[k] += res[k]
    return acc

async def _process_external_members(batch_handler):
    acc = {"active": 0, "dormant": 0, "unknown": 0, "total": 0}
    batch = []
    try:
        async for f_member in fielia_service.stream_all_members():
            batch.append(f_member)
            if len(batch) >= 100:
                res = await batch_handler(batch)
                for k in acc: acc[k] += res[k]
                batch = []
        if batch:
            res = await batch_handler(batch)
            for k in acc: acc[k] += res[k]
    except (ConnectionError, asyncio.TimeoutError) as e:
        print(f"  ! Network error fetching Fielia members: {e}")
    except Exception as e:
        print(f"  ! Unexpected error fetching Fielia members: {e}")
    return acc

async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    try:
        # Robust URI parsing for database name
        if settings.mongodb_db_name:
            db_name = settings.mongodb_db_name
        else:
            parsed = urlparse(settings.mongodb_url)
            db_name = parsed.path.lstrip("/") or "restobuzz"
            
        db = client[db_name]

        cutoff = datetime.now(timezone.utc) - timedelta(days=DORMANCY_DAYS)

        print("")
        print("=" * 70)
        print("  ABSOLUTE DEEP DORMANCY AUDIT (Internal + Fielia External + Logs)")
        print(f"  Cutoff: {cutoff.strftime('%Y-%m-%d %H:%M')} UTC")
        print("=" * 70)
        print("")

        restaurants = await db.restaurants.find({}, {"id": 1, "name": 1}).to_list(None)

        for rest in restaurants:
            await _process_restaurant(db, rest, cutoff)

        print("=" * 70)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
