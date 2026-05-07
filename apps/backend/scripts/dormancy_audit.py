"""
Absolute Deep Dormancy Audit.
Checks:
1. Internal members (All restaurants)
2. Fielia External members (Restaurant r2 only)
3. Historical logs (reservego_bill_data / uploads)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.config import settings
from app.services.dormancy_service import dormancy_service, normalize_phone_for_match
from app.services.fielia_members_service import fielia_service

DORMANCY_DAYS = 30


async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.rsplit("/", 1)[-1].split("?")[0]
    db = client[db_name]

    cutoff = datetime.now(timezone.utc) - timedelta(days=DORMANCY_DAYS)

    print("")
    print("=" * 70)
    print("  ABSOLUTE DEEP DORMANCY AUDIT (Internal + Fielia External + Logs)")
    print("  Cutoff: %s UTC" % cutoff.strftime("%Y-%m-%d %H:%M"))
    print("=" * 70)
    print("")

    restaurants = await db.restaurants.find({}, {"id": 1, "name": 1}).to_list(None)

    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        name = rest.get("name", rid)

        # 1. Collect all members (Internal + Fielia External)
        members = await db.members.find({"restaurant_id": rid}).to_list(None)
        
        # If r2, fetch from Fielia DB too
        if rid == "r2":
            try:
                # Use the stream to get all Fielia members
                async for f_member in fielia_service.stream_all_members():
                    members.append(f_member)
            except Exception as e:
                print("  ! Error fetching Fielia members: %s" % e)

        if not members:
            continue

        total_members = len(members)
        active_count = 0
        dormant_count = 0
        unknown_count = 0

        # Process batches
        batch_size = 100
        for i in range(0, len(members), batch_size):
            batch = members[i : i + batch_size]
            phones = [m.get("phone") for m in batch]
            uuids = [m.get("card_uid") for m in batch]

            activity_map = await dormancy_service.get_bulk_activity(db, rid, phones, uuids)

            for m in batch:
                # Check for activity in member profile
                lv_candidates = []
                
                # Internal visit field
                raw_lv = m.get("last_visit")
                if raw_lv:
                    if isinstance(raw_lv, str):
                        try: raw_lv = datetime.fromisoformat(raw_lv.replace("Z", "+00:00"))
                        except: raw_lv = None
                    if raw_lv: lv_candidates.append(raw_lv)

                # External log match
                norm_phone = normalize_phone_for_match(m.get("phone"))
                uuid_val = m.get("card_uid")
                external_activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
                if external_activity:
                    lv_candidates.append(external_activity[0])

                if not lv_candidates:
                    unknown_count += 1
                    continue
                
                final_lv = max(lv_candidates)
                if final_lv.tzinfo is None:
                    final_lv = final_lv.replace(tzinfo=timezone.utc)
                
                if final_lv >= cutoff:
                    active_count += 1
                else:
                    dormant_count += 1

        print("  Restaurant : %s (%s)" % (name, rid))
        print("  Total Pool : %d  (Internal + External)" % total_members)
        print("  Active     : %d" % active_count)
        print("  DORMANT    : %d  <-- Matching UI" % dormant_count)
        print("  Unknown    : %d" % unknown_count)
        print("")

    print("=" * 70)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
